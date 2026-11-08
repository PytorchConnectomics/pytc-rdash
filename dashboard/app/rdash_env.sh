# Bash helper: parse data, never execute an environment file.
rdash_load_env() {
    local file=${RDASH_ENV_FILE:-$HOME/.config/rdash/env} line key value
    [[ -e $file ]] || return 0
    while IFS= read -r line || [[ -n $line ]]; do
        [[ $line =~ ^[[:space:]]*$ || $line =~ ^[[:space:]]*# ]] && continue
        if [[ ! $line =~ ^(RDASH_HOST|RDASH_REMOTE_ROOT|RDASH_SSH_HOSTS|RDASH_GPU_ROOT|RDASH_CONFIG_DIR|RESEARCH_DASH_PORT)=[A-Za-z0-9._,/-]*$ ]]; then
            echo 'rdash: invalid environment file line' >&2
            return 1
        fi
        key=${line%%=*}; value=${line#*=}
        if ! declare -p "$key" >/dev/null 2>&1; then printf -v "$key" '%s' "$value"; fi
        export "$key"
    done < "$file"
}
rdash_load_env || exit 1
