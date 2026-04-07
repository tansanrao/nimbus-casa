#!/usr/bin/env bash

set -euo pipefail

if ! command -v kubectl >/dev/null 2>&1; then
  echo "kubectl is required" >&2
  exit 1
fi

if ! command -v jq >/dev/null 2>&1; then
  echo "jq is required" >&2
  exit 1
fi

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

exclude_reason() {
  local namespace="$1"
  local name="$2"

  case "${namespace}/${name}" in
    default/immich-nfs-pvc)
      printf '%s\n' "Backed up outside VolSync on the Immich NFS path"
      return 0
      ;;
    media/mediastore-nfs-pvc)
      printf '%s\n' "Backed up outside VolSync on the mediastore NFS path"
      return 0
      ;;
    media/jellystat)
      printf '%s\n' "Jellystat is stateless here; the chart only mounts emptyDir storage"
      return 0
      ;;
  esac

  if [[ "$namespace" == "database" && "$name" =~ ^(immich16-postgres-.*-pgdata|postgres16-postgres-.*-pgdata)$ ]]; then
    printf '%s\n' "Protected by pgBackRest and WAL archiving to S3"
    return 0
  fi

  return 1
}

printf '== VolSync + OpenEBS-LVM Audit ==\n'
printf 'Repo: %s\n' "$repo_root"
printf 'Context: %s\n\n' "$(kubectl config current-context)"

declare -a openebs_pvcs=()
while IFS= read -r line; do
  openebs_pvcs+=("$line")
done < <(
  kubectl get pvc -A -o json |
    jq -r '
      .items[]
      | select(.spec.storageClassName == "openebs-lvm")
      | "\(.metadata.namespace)\t\(.metadata.name)\t\(.status.phase // "Unknown")"
    ' |
    sort
)

declare -a rep_sources=()
while IFS= read -r line; do
  rep_sources+=("$line")
done < <(
  kubectl get replicationsources.volsync.backube -A -o json |
    jq -r '.items[] | "\(.metadata.namespace)/\(.metadata.name)"' |
    sort
)

declare -a rep_destinations=()
while IFS= read -r line; do
  rep_destinations+=("$line")
done < <(
  kubectl get replicationdestinations.volsync.backube -A -o json |
    jq -r '.items[] | "\(.metadata.namespace)/\(.metadata.name)"' |
    sort
)

declare -a protected=()
declare -a excluded=()
declare -a gaps=()
declare -a issues=()

for entry in "${openebs_pvcs[@]}"; do
  IFS=$'\t' read -r namespace name phase <<<"$entry"
  key="${namespace}/${name}"

  if reason="$(exclude_reason "$namespace" "$name")"; then
    excluded+=("${key} [${phase}] - ${reason}")
    continue
  fi

  if printf '%s\n' "${rep_sources[@]}" | grep -qx "$key"; then
    protected+=("${key} [${phase}]")
    if [[ "$phase" != "Bound" ]]; then
      issues+=("${key} is VolSync-managed but PVC phase is ${phase}")
    fi
    continue
  fi

  gaps+=("${key} [${phase}]")
done

printf '%s\n' 'Protected OpenEBS PVCs'
for item in "${protected[@]-}"; do
  [[ -n "$item" ]] || continue
  printf '  - %s\n' "$item"
done
[[ ${#protected[@]} -gt 0 ]] || printf '  - none\n'
printf '\n'

printf '%s\n' 'Excluded PVCs'
for item in "${excluded[@]-}"; do
  [[ -n "$item" ]] || continue
  printf '  - %s\n' "$item"
done
[[ ${#excluded[@]} -gt 0 ]] || printf '  - none\n'
printf '\n'

printf '%s\n' 'Unintended Gaps'
for item in "${gaps[@]-}"; do
  [[ -n "$item" ]] || continue
  printf '  - %s\n' "$item"
done
[[ ${#gaps[@]} -gt 0 ]] || printf '  - none\n'
printf '\n'

printf '%s\n' 'Replication Sources'
kubectl get replicationsources.volsync.backube -A \
  -o custom-columns='NAMESPACE:.metadata.namespace,NAME:.metadata.name,SOURCE:.spec.sourcePVC,LAST_SYNC:.status.lastSyncTime,DURATION:.status.lastSyncDuration' \
  --no-headers | sed 's/^/  - /'
printf '\n'

printf '%s\n' 'Replication Destinations'
kubectl get replicationdestinations.volsync.backube -A \
  -o custom-columns='NAMESPACE:.metadata.namespace,NAME:.metadata.name,DEST:.spec.restic.destinationPVC,LAST_SYNC:.status.lastSyncTime,DURATION:.status.lastSyncDuration' \
  --no-headers | sed 's/^/  - /'
printf '\n'

printf '%s\n' 'OpenEBS Thin Pool'
kubectl get lvmnodes.local.openebs.io -A -o json |
  jq -r '
    .items[]
    | .metadata.name as $node
    | .volumeGroups[]
    | .thinPools[]
    | "  - node=\($node) thinpool=\(.name) free=\(.free) size=\(.size)"
  '
printf '\n'

printf '%s\n' 'Released PVs'
kubectl get pv -o json |
  jq -r '
    .items[]
    | select(.status.phase == "Released")
    | "  - \(.metadata.name) claim=\(.spec.claimRef.namespace // "-")/\(.spec.claimRef.name // "-") storageClass=\(.spec.storageClassName // "-")"
  '
printf '\n'

printf '%s\n' 'Audit Issues'
for item in "${issues[@]-}"; do
  [[ -n "$item" ]] || continue
  printf '  - %s\n' "$item"
done
[[ ${#issues[@]} -gt 0 ]] || printf '  - none\n'
