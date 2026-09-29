#!/usr/bin/env bash
set -euo pipefail

# Ansible invokes this entire rollout under nexus-grokmirror.lock. The
# scheduled mirror cannot read a new token while the old server still runs.
checkout=$1
app_enabled=$2
force_recreate=${3:-false}
staging=/opt/nexus/.deploy

install_managed() {
    local source=$1 destination=$2 mode=$3
    if ! cmp -s "$source" "$destination" ||
        [[ $(stat -c '%a:%u:%g' "$destination" 2>/dev/null) != "${mode#0}:0:0" ]]; then
        install -o root -g root -m "$mode" "$source" "$destination"
        echo NEXUS_DEPLOY_CHANGED
    fi
}

install_managed "$staging/nexus.env" /opt/nexus/nexus.env 0600
install_managed "$staging/maintenance.env" /etc/default/nexus 0600
install_managed "$staging/run-grokmirror.sh" /usr/local/sbin/nexus-grokmirror 0755
install_managed "$staging/grokmirror.conf" /opt/nexus/lore/grokmirror.conf 0644

cd "$checkout"
compose=(docker compose --env-file /opt/nexus/nexus.env)
"${compose[@]}" up --detach --wait db

if [[ $app_enabled == true ]]; then
    test "$(git --git-dir=/opt/nexus/mainline.git rev-parse --is-bare-repository)" = true
    # Creating a transient migration container is not a deployment change;
    # Ansible recognizes actual migrations by "Applying:" on stdout.
    "${compose[@]}" run --rm migrate 2>&1
    recreate_args=()
    if [[ $force_recreate == true ]]; then
        recreate_args=(--force-recreate --no-deps)
    fi
    "${compose[@]}" up --detach --wait "${recreate_args[@]}" server worker web
    curl --fail --silent --show-error http://127.0.0.1:8080/api/v1/mailing-lists >/dev/null

    # Read-only checks: never enqueue maintenance to test authentication. Send
    # the bearer header through stdin so it does not appear in process listings.
    source /etc/default/nexus
    admin_url=http://127.0.0.1:8080/api/v1/admin/mainline
    test "$(curl --silent --show-error --output /dev/null --write-out '%{http_code}' "$admin_url")" = 401
    authenticated_status=$(
        printf 'Authorization: Bearer %s\n' "$NEXUS_ADMIN_TOKEN" |
            curl --header @- --fail --silent --show-error --output /dev/null --write-out '%{http_code}' "$admin_url"
    )
    test "$authenticated_status" = 200
fi
