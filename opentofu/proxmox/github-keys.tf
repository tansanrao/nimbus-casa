# SSH keys for new VMs' cloud-init user: the public keys of the GitHub users
# listed in authorized_users at the repository root. Ansible's ssh_access role
# keeps the login account's keys in sync with the same file.
locals {
  github_users = [
    for line in split("\n", file("${path.module}/../../authorized_users")) : trimspace(line)
    if trimspace(line) != "" && !startswith(trimspace(line), "#")
  ]
}

data "http" "github_keys" {
  for_each = toset(local.github_users)
  url      = "https://github.com/${each.key}.keys"

  lifecycle {
    postcondition {
      condition     = self.status_code == 200 && length(regexall("(?m)^ssh-", self.response_body)) > 0
      error_message = "GitHub user ${each.key} returned no SSH keys."
    }
  }
}

locals {
  github_ssh_keys = flatten([
    for user in local.github_users : [
      for key in split("\n", trimspace(data.http.github_keys[user].response_body)) :
      "${trimspace(key)} github:${user}" if startswith(trimspace(key), "ssh-")
    ]
  ])
}
