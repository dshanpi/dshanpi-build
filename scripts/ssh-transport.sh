#!/usr/bin/env bash
# Sourced by the CI fetch/publish entry points; credentials are never printed.
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib.sh"

apt_ssh_init() {
    local variable value
    # Pasted connection fields can have surrounding spaces or CRLF. Passwords
    # are opaque: never trim or otherwise transform PASSWORD.
    for variable in HOST USERNAME PORT; do
        value=${!variable:-}
        value="${value#"${value%%[![:space:]]*}"}"
        value="${value%"${value##*[![:space:]]}"}"
        printf -v "$variable" '%s' "$value"
    done
    for variable in HOST USERNAME PASSWORD PORT; do
        [[ -n "${!variable:-}" ]] || die "$variable is required"
    done
    [[ "$HOST" =~ ^[a-zA-Z0-9][a-zA-Z0-9.-]*$ ]] || die "HOST must be a hostname or IPv4 address without protocol, path, username or port"
    [[ "$USERNAME" =~ ^[a-zA-Z0-9_][a-zA-Z0-9_.-]*$ ]] || die "invalid USERNAME"
    [[ "$PORT" =~ ^[0-9]{1,5}$ ]] && ((10#$PORT >= 1 && 10#$PORT <= 65535)) || die "invalid PORT"
    require_command sshpass
    require_command rsync
    apt_server_root=${APT_SERVER_ROOT:-/www/wwwroot/apt.100ask.net}
    [[ "$apt_server_root" =~ ^/[a-zA-Z0-9_./-]+$ && "$apt_server_root" != / && "$apt_server_root" != */../* && "$apt_server_root" != */.. ]] || die "invalid APT_SERVER_ROOT"
    mkdir -p "$repo_root/output"
    # Only four secrets are needed. Persist the first observed host key across
    # fetch and publish in this checkout, and reject changes during the job.
    apt_known_hosts="$repo_root/output/apt-known-hosts"
    (umask 077; touch "$apt_known_hosts")
    if [[ -s "$repo_root/keys/apt-server-known-hosts" ]]; then
        cp "$repo_root/keys/apt-server-known-hosts" "$apt_known_hosts"
    fi
    export SSHPASS=$PASSWORD
    apt_remote="$USERNAME@$HOST"
    apt_ssh_options=(-p "$PORT" -o StrictHostKeyChecking=accept-new
        -o "UserKnownHostsFile=$apt_known_hosts" -o ConnectTimeout=30
        -o ServerAliveInterval=15 -o ServerAliveCountMax=4 -o LogLevel=ERROR)
    # The rsync invocation already has sshpass. Nesting it here would read
    # the scrubbed SSHPASS inherited from the outer process and send a bad password.
    printf -v apt_rsync_shell '%q ' ssh "${apt_ssh_options[@]}"
}

apt_remote_run() {
    local command argument
    command='python3 - --'
    for argument in "$@"; do
        printf -v command '%s %q' "$command" "$argument"
    done
    sshpass -e ssh "${apt_ssh_options[@]}" "$apt_remote" "$command" < "$script_dir/ssh-repository.py"
}
