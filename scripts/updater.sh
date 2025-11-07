#!/usr/bin/env bash
# Docker script updater for homelabs
# Licencia: MIT

# ————————————————
# Modo estricto + helpers
# ————————————————
set -Eeuo pipefail
shopt -s nullglob dotglob

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)"
DEFAULT_CONF=
for candidate in "$SCRIPT_DIR/../config/updater.conf" "$SCRIPT_DIR/config/updater.conf" "$SCRIPT_DIR/updater.conf"; do
  if [[ -z "$DEFAULT_CONF" && -f "$candidate" ]]; then
    DEFAULT_CONF="$candidate"
  fi
done
CONF_FILE="${CONF_FILE:-"${DEFAULT_CONF:-"$SCRIPT_DIR/../config/updater.conf"}"}"

# Colores (desactivables con NO_COLOR=1)
if [[ "${NO_COLOR:-0}" != 1 && -t 1 ]]; then
  C_RED='\033[0;31m'; C_GRN='\033[0;32m'; C_YLW='\033[0;33m'; C_BLU='\033[0;34m'; C_DIM='\033[2m'; C_RST='\033[0m'
else
  C_RED=; C_GRN=; C_YLW=; C_BLU=; C_DIM=; C_RST=
fi

log()   { printf "%b[%s] %s%b\n" "$C_DIM" "$(date +%F' '%T)" "$*" "$C_RST"; }
info()  { printf "%b[i]%b %s\n"  "$C_BLU" "$C_RST" "$*"; }
ok()    { printf "%b[✓]%b %s\n"  "$C_GRN" "$C_RST" "$*"; }
warn()  { printf "%b[!]%b %s\n"  "$C_YLW" "$C_RST" "$*"; }
err()   { printf "%b[x]%b %s\n"  "$C_RED" "$C_RST" "$*"; }

die()   { err "$*"; exit 1; }

html_escape() {
  local str="${1-}"
  str=${str//&/&amp;}
  str=${str//</&lt;}
  str=${str//>/&gt;}
  str=${str//\"/&quot;}
  str=${str//\'/&#39;}
  printf '%s' "$str"
}

mime_quote() {
  local str="${1-}"
  str=${str//\\/\\\\}
  str=${str//\"/\\\"}
  printf '%s' "$str"
}

# ————————————————
# Carga de configuración
# ————————————————
if [[ -f "$CONF_FILE" ]]; then
  # shellcheck disable=SC1090
  source "$CONF_FILE"
else
  warn "No existe $CONF_FILE; usando defaults razonables"
fi

# Defaults si no están en el conf
BASE_DIR=${BASE_DIR:-/srv/compose}
LOG_DIR=${LOG_DIR:-/var/log/docker-updater}
LOCK_FILE=${LOCK_FILE:-/var/lock/docker-updater.lock}
EMAIL_TO=${EMAIL_TO:-""}
EMAIL_FROM=${EMAIL_FROM:-"homelab@localhost"}
SUBJECT_PREFIX=${SUBJECT_PREFIX:-"[docker-updater]"}
DOCKER_TIMEOUT=${DOCKER_TIMEOUT:-120}
PRUNE_ENABLED=${PRUNE_ENABLED:-false}
PRUNE_VOLUMES=${PRUNE_VOLUMES:-false}
PRUNE_FILTER_UNTIL=${PRUNE_FILTER_UNTIL:-""} # ej: 168h
ATTACH_LOGS_ON=${ATTACH_LOGS_ON:-changes}    # changes|always|never
QUIET_PULL=${QUIET_PULL:-true}
PULL_POLICY=${PULL_POLICY:-always}          # always|missing|never
PARALLEL_PULL=${PARALLEL_PULL:-0}           # 0 = por defecto de Docker
DRY_RUN=${DRY_RUN:-false}
LOG_RETENTION_DAYS=${LOG_RETENTION_DAYS:-14}
EXCLUDE_PATTERNS_RAW=${EXCLUDE_PATTERNS:-".git node_modules backup tmp"}
read -r -a EXCLUDE_PATTERNS <<< "$EXCLUDE_PATTERNS_RAW"
COMPOSE_PROJECTS_FILE=${COMPOSE_PROJECTS_FILE:-""}
SMTP_CMD=${SMTP_CMD:-msmtp}                  # msmtp|mailx|sendmail
SMTP_ACCOUNT=${SMTP_ACCOUNT:-default}
SMTP_READ_ENVELOPE=${SMTP_READ_ENVELOPE:-true}

# ————————————————
# Lock para evitar solapes
# ————————————————
mkdir -p "$(dirname "$LOCK_FILE")"
exec 9>"$LOCK_FILE" || die "No puedo abrir lock $LOCK_FILE"
if ! flock -n 9; then
  warn "Otra ejecución está en curso; salgo"
  exit 0
fi

# ————————————————
# Detección de docker compose
# ————————————————
version_ge() {
  local v1="${1#v}" v2="${2#v}" highest
  [[ "$v1" == "$v2" ]] && return 0
  highest=$(printf '%s\n%s\n' "$v1" "$v2" | LC_ALL=C sort -V | tail -n1)
  [[ "$highest" == "$v1" ]]
}

get_compose_version() {
  local -a cmd=("$@")
  local version_str version_out
  if version_str=$("${cmd[@]}" version --short 2>/dev/null); then
    printf '%s' "$version_str"
    return 0
  fi
  if version_out=$("${cmd[@]}" version 2>/dev/null); then
    if [[ $version_out =~ ([0-9]+([.][0-9]+)+) ]]; then
      printf '%s' "${BASH_REMATCH[1]}"
      return 0
    fi
  fi
  return 1
}

compose_wait_flag_present() {
  local -a cmd=("$@")
  "${cmd[@]}" up --help 2>&1 | grep -q -- '--wait'
}

compose_quiet_pull_flag_present() {
  local -a cmd=("$@")
  "${cmd[@]}" up --help 2>&1 | grep -q -- '--quiet-pull'
}

MIN_COMPOSE_WAIT_VERSION=${MIN_COMPOSE_WAIT_VERSION:-"2.17.0"}

COMPOSE_BIN=${COMPOSE_BIN:-""}
COMPOSE_SUPPORTS_WAIT=false
COMPOSE_SUPPORTS_QUIET_PULL=false
COMPOSE_SUPPORTS_PULL_POLICY=true
if [[ -z "$COMPOSE_BIN" ]]; then
  if docker compose version &>/dev/null; then
    COMPOSE_BIN="docker compose"
  elif command -v docker-compose &>/dev/null; then
    COMPOSE_BIN="docker-compose"
    COMPOSE_SUPPORTS_PULL_POLICY=false
  else
    die "Necesitas Docker con plugin 'compose' o docker-compose v1"
  fi
fi

read -r -a _compose_check <<<"$COMPOSE_BIN"
if compose_version=$(get_compose_version "${_compose_check[@]}"); then
  compose_version=${compose_version#v}
  if [[ "${compose_version%%.*}" -ge 2 ]]; then
    COMPOSE_SUPPORTS_PULL_POLICY=true
    if version_ge "$compose_version" "$MIN_COMPOSE_WAIT_VERSION" && compose_wait_flag_present "${_compose_check[@]}"; then
      COMPOSE_SUPPORTS_WAIT=true
    fi
    if compose_quiet_pull_flag_present "${_compose_check[@]}"; then
      COMPOSE_SUPPORTS_QUIET_PULL=true
    fi
  else
    COMPOSE_SUPPORTS_PULL_POLICY=false
  fi
else
  if [[ "${_compose_check[*]}" == docker\ compose* ]]; then
    COMPOSE_SUPPORTS_PULL_POLICY=true
    if compose_wait_flag_present "${_compose_check[@]}"; then
      COMPOSE_SUPPORTS_WAIT=true
    fi
    if compose_quiet_pull_flag_present "${_compose_check[@]}"; then
      COMPOSE_SUPPORTS_QUIET_PULL=true
    fi
  elif [[ "${_compose_check[*]}" == docker-compose* ]]; then
    COMPOSE_SUPPORTS_PULL_POLICY=false
  else
    COMPOSE_SUPPORTS_PULL_POLICY=true
    if compose_quiet_pull_flag_present "${_compose_check[@]}"; then
      COMPOSE_SUPPORTS_QUIET_PULL=true
    fi
  fi
fi

if [[ "$COMPOSE_SUPPORTS_WAIT" != true ]]; then
  warn "El comando '${_compose_check[*]}' no soporta '--wait'; se omitirá"
fi

if [[ "$QUIET_PULL" == true && "$COMPOSE_SUPPORTS_QUIET_PULL" != true ]]; then
  warn "El comando '${_compose_check[*]}' no soporta '--quiet-pull'; se omitirá"
fi

unset _compose_check

read -r -a COMPOSE_CMD <<<"$COMPOSE_BIN"

# Concurrencia de pulls
if (( PARALLEL_PULL > 0 )); then
  export COMPOSE_PARALLEL_LIMIT="$PARALLEL_PULL"
fi

# ————————————————
# Utilidades
# ————————————————
RUN_CMDS=()
run() {
  local stdin_file="${RUN_STDIN_FILE:-}" stdin_text="${RUN_STDIN_TEXT:-}" stdin_label="${RUN_STDIN_LABEL:-}" cmd_display status was_errexit=0
  unset RUN_STDIN_FILE RUN_STDIN_TEXT RUN_STDIN_LABEL

  if (($# == 0)); then
    return 0
  fi

  printf -v cmd_display '%q ' "$@"
  cmd_display=${cmd_display::-1}

  if [[ -n "$stdin_file" ]]; then
    cmd_display+=" <$(printf '%q' "$stdin_file")"
  elif [[ -n "$stdin_text" ]]; then
    local label="${stdin_label:-stdin-text}"
    cmd_display+=" <<<$(printf '%q' "$label")"
  fi

  RUN_CMDS+=("$cmd_display")
  if [[ "$DRY_RUN" == true ]]; then
    info "(dry-run) $cmd_display"
    return 0
  fi

  if [[ $- == *e* ]]; then
    was_errexit=1
    set +e
  fi

  if [[ -n "$stdin_file" ]]; then
    "$@" <"$stdin_file"
  elif [[ -n "$stdin_text" ]]; then
    "$@" <<<"$stdin_text"
  else
    "$@"
  fi
  status=$?

  if (( was_errexit )); then
    set -e
  fi

  return $status
}

get_compose_file() {
  local dir="$1"
  for f in compose.yaml compose.yml docker-compose.yaml docker-compose.yml; do
    [[ -f "$dir/$f" ]] && { echo "$dir/$f"; return 0; }
  done
  return 1
}

# ¿El directorio está excluido por patrón simple?
is_excluded() {
  local dir="$1"; local name="$(basename "$dir")"
  for p in "${EXCLUDE_PATTERNS[@]}"; do
    [[ -z "$p" ]] && continue
    [[ "$dir" == *"/$p"* || "$name" == "$p" ]] && return 0
  done
  return 1
}

# Captura IDs de imagen actuales por servicio (concatenados si hay réplicas)
# Salida: imprime "servicio|imgid1,imgid2,..."
capture_images() {
  local compose_file="$1"
  if ! mapfile -t services < <("${COMPOSE_CMD[@]}" -f "$compose_file" config --services); then
    warn "No se pudieron listar servicios en $(dirname "$compose_file")"
    return 1
  fi
  for s in "${services[@]}"; do
    if ! mapfile -t cids < <("${COMPOSE_CMD[@]}" -f "$compose_file" ps -q "$s"); then
      warn "No se pudieron obtener contenedores del servicio '$s' en $(dirname "$compose_file")"
      return 1
    fi
    if ((${#cids[@]})); then
      local imgs=()
      for cid in "${cids[@]}"; do
        imgs+=("$(docker inspect --format '{{.Image}}' "$cid" 2>/dev/null || true)")
      done
      printf '%s|%s\n' "$s" "${imgs[*]:-}"
    else
      printf '%s|\n' "$s"
    fi
  done
}

# Healthcheck: exige healthy si el contenedor define healthcheck; si no, exige running
healthcheck_project() {
  local compose_file="$1"; local ok=0
  if ! mapfile -t ids < <("${COMPOSE_CMD[@]}" -f "$compose_file" ps -q); then
    warn "No se pudieron obtener contenedores en $(dirname "$compose_file")"
    return 1
  fi
  ((${#ids[@]})) || { warn "Sin contenedores en $(dirname "$compose_file")"; return 1; }
  for id in "${ids[@]}"; do
    local hc status
    hc=$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' "$id" 2>/dev/null || echo none)
    status=$(docker inspect --format '{{.State.Status}}' "$id" 2>/dev/null || echo unknown)
    if [[ "$hc" != none && "$hc" != healthy ]]; then ok=1; break; fi
    if [[ "$hc" == none && "$status" != running ]]; then ok=1; break; fi
  done
  [[ $ok -eq 0 ]]
}

# Email: construye MIME multipart/alternative y adjunta ficheros
send_email() {
  local subject="$1"; local text="$2"; local html="$3"; shift 3
  local attachments=("$@")
  [[ -z "$EMAIL_TO" ]] && { warn "EMAIL_TO vacío; no envío correo"; return 0; }

  local bnd="bnd_$(date +%s)_$$"
  local alt="alt_$(date +%s)_$$"
  local tmpmsg
  tmpmsg="$(mktemp)"
  trap 'rm -f "$tmpmsg"; trap - RETURN' RETURN

  {
    echo "From: $EMAIL_FROM"
    echo "To: $EMAIL_TO"
    echo "Subject: $subject"
    echo "MIME-Version: 1.0"
    echo "Content-Type: multipart/mixed; boundary=\"$bnd\""
    echo
    echo "--$bnd"
    echo "Content-Type: multipart/alternative; boundary=\"$alt\""
    echo
    echo "--$alt"
    echo "Content-Type: text/plain; charset=UTF-8"
    echo "Content-Transfer-Encoding: 8bit"
    echo
    printf '%s\n' "$text"
    echo
    echo "--$alt"
    echo "Content-Type: text/html; charset=UTF-8"
    echo "Content-Transfer-Encoding: 8bit"
    echo
    printf '%s\n' "$html"
    echo
    echo "--$alt--"

    local base_name base_name_escaped
    for f in "${attachments[@]}"; do
      [[ -f "$f" ]] || continue
      base_name="$(basename "$f")"
      base_name_escaped="$(mime_quote "$base_name")"
      echo "--$bnd"
      printf 'Content-Type: application/octet-stream; name="%s"\n' "$base_name_escaped"
      printf 'Content-Disposition: attachment; filename="%s"\n' "$base_name_escaped"
      echo "Content-Transfer-Encoding: base64"
      echo
      base64 "$f"
      echo
    done

    echo "--$bnd--"
  } >"$tmpmsg"

  case "$SMTP_CMD" in
    msmtp)
      local -a msmtp_cmd=(msmtp)
      if [[ "$SMTP_READ_ENVELOPE" == true ]]; then
        msmtp_cmd+=(--read-envelope-from)
      fi
      msmtp_cmd+=(-a "$SMTP_ACCOUNT" -t)
      RUN_STDIN_FILE="$tmpmsg" run "${msmtp_cmd[@]}"
      ;;
    mailx)
      # Fallback simple (sin multipart bonito); enviamos solo texto
      RUN_STDIN_TEXT="$text" RUN_STDIN_LABEL="mailx-body" run mailx -s "$subject" "$EMAIL_TO"
      ;;
    sendmail)
      RUN_STDIN_FILE="$tmpmsg" run sendmail -t
      ;;
    *)
      warn "SMTP_CMD desconocido ($SMTP_CMD); no envío correo"
      ;;
  esac

  rm -f "$tmpmsg"
  trap - RETURN
}

# ————————————————
# Main
# ————————————————
mkdir -p "$LOG_DIR"

# Recolecta proyectos
PROJECT_DIRS=()
if [[ -n "$COMPOSE_PROJECTS_FILE" ]]; then
  if [[ -r "$COMPOSE_PROJECTS_FILE" ]]; then
    while IFS= read -r line; do
      line="${line#"${line%%[![:space:]]*}"}"
      line="${line%"${line##*[![:space:]]}"}"
      [[ -z "$line" || $line == \#* ]] && continue
      PROJECT_DIRS+=("$line")
    done < "$COMPOSE_PROJECTS_FILE"
  else
    die "COMPOSE_PROJECTS_FILE ($COMPOSE_PROJECTS_FILE) no existe o no es legible"
  fi
else
  usable_patterns=()
  for pat in "${EXCLUDE_PATTERNS[@]}"; do
    [[ -z "$pat" ]] && continue
    usable_patterns+=("$pat")
  done

  # Importante: mantener la forma `find "$BASE_DIR" \( … \) -prune -o -type d -print0`
  # porque `find` es muy sensible a los paréntesis de agrupación.
  find_cmd=(find "$BASE_DIR")
  if ((${#usable_patterns[@]})); then
    find_cmd+=('(')
    for idx in "${!usable_patterns[@]}"; do
      pat="${usable_patterns[$idx]}"
      (( idx > 0 )) && find_cmd+=(-o)
      find_cmd+=(-path "*/$pat")
    done
    find_cmd+=(')')
    find_cmd+=(-prune -o)
  fi
  find_cmd+=(-type d -print0)

  while IFS= read -r -d '' d; do
    is_excluded "$d" && continue
    PROJECT_DIRS+=("$d")
  done < <("${find_cmd[@]}")
fi

[[ ${#PROJECT_DIRS[@]} -eq 0 ]] && die "No se encontraron proyectos bajo $BASE_DIR"

changed_projects=()
failed_projects=()
proj_logs=()
declare -A project_logs=()
declare -A project_display_names=()
declare -A project_hashes=()
project_order=()

start_ts=$(date +%s)

for dir in "${PROJECT_DIRS[@]}"; do
  compose_file="$(get_compose_file "$dir" || true)"
  [[ -f "$compose_file" ]] || continue

  project_name="$(basename "$dir")"
  project_key="$dir"
  project_order+=("$project_key")
  dir_hash=$(sha1sum <<<"$dir" | cut -c1-8)
  printf -v proj_log '%s/%s_%(%Y%m%d-%H%M%S)T_%s.log' \
    "$LOG_DIR" "$project_name" -1 "$dir_hash"
  proj_logs+=("$proj_log")
  project_logs["$project_key"]="$proj_log"
  project_display_names["$project_key"]="$project_name"
  project_hashes["$project_key"]="$dir_hash"

  {
    log "Proyecto: $project_name"
    log "Archivo Compose: $compose_file"

    # Snapshot antes
    declare -A before=()
    tmp_before="$(mktemp)"
    if ! capture_images "$compose_file" >"$tmp_before"; then
      before_status=$?
      warn "No se pudo capturar estado inicial en $project_name (código $before_status)"
      failed_projects+=("$project_key")
      rm -f "$tmp_before"
      continue
    fi
    while IFS='|' read -r svc imgs; do
      before["$svc"]="$imgs"
    done <"$tmp_before"
    rm -f "$tmp_before"

    # Pull + up (moderno)
    do_explicit_pull=true
    pull_skip_reason=""
    if [[ "$PULL_POLICY" == never ]]; then
      do_explicit_pull=false
      pull_skip_reason="PULL_POLICY=never"
    elif [[ "$PULL_POLICY" == missing && "$COMPOSE_SUPPORTS_PULL_POLICY" == true ]]; then
      do_explicit_pull=false
      pull_skip_reason="PULL_POLICY=missing (se confía en 'up --pull missing')"
    fi

    if [[ "$do_explicit_pull" == true ]]; then
      pull_args=("${COMPOSE_CMD[@]}" -f "$compose_file" pull)
      if [[ $QUIET_PULL == true ]]; then
        pull_args+=(--quiet)
      fi
      if ! run "${pull_args[@]}"; then
        pull_status=$?
        warn "'docker compose pull' falló en $project_name (código $pull_status)"
        failed_projects+=("$project_key")
        continue
      fi
    else
      info "Omitiendo 'docker compose pull' ($pull_skip_reason)"
    fi

    up_args=("${COMPOSE_CMD[@]}" -f "$compose_file" up -d)
    if [[ "$COMPOSE_SUPPORTS_PULL_POLICY" == true ]]; then
      # docker compose V2 acepta --pull, docker-compose V1 no; si no está soportado
      # confiamos en el pull previo para refrescar imágenes
      up_args+=(--pull "$PULL_POLICY")
    fi
    if [[ $QUIET_PULL == true && "$COMPOSE_SUPPORTS_QUIET_PULL" == true ]]; then
      up_args+=(--quiet-pull)
    fi
    up_args+=(--remove-orphans)
    if [[ "$COMPOSE_SUPPORTS_WAIT" == true ]]; then
      up_args+=(--wait --wait-timeout "$DOCKER_TIMEOUT")
    fi
    up_args+=(-t "$DOCKER_TIMEOUT")
    if ! run "${up_args[@]}"; then
      warn "'docker compose up' falló en $project_name"
      failed_projects+=("$project_key")
      continue
    fi

    # Snapshot después
    declare -A after=()
    tmp_after="$(mktemp)"
    if ! capture_images "$compose_file" >"$tmp_after"; then
      after_status=$?
      warn "No se pudo capturar estado posterior en $project_name (código $after_status)"
      failed_projects+=("$project_key")
      rm -f "$tmp_after"
      continue
    fi
    while IFS='|' read -r svc imgs; do
      after["$svc"]="$imgs"
    done <"$tmp_after"
    rm -f "$tmp_after"

    # ¿Hubo cambios?
    changed=false
    for k in "${!after[@]}"; do
      if [[ "${before[$k]:-}" != "${after[$k]:-}" ]]; then changed=true; fi
    done

    # Healthcheck real
    if ! healthcheck_project "$compose_file"; then
      warn "Healthcheck falló en $project_name"
      failed_projects+=("$project_key")
    fi

    if [[ "$changed" == true ]]; then
      ok "Actualizado: $project_name"
      changed_projects+=("$project_key")
    else
      info "Sin cambios en imágenes para $project_name"
    fi

  } &>"$proj_log"

done

# Limpieza de logs antiguos
find "$LOG_DIR" -type f -name "*.log" -mtime +"$LOG_RETENTION_DAYS" -delete || true

# Prune (opcional)
if [[ "$PRUNE_ENABLED" == true && "$DRY_RUN" != true ]]; then
  if [[ -n "$PRUNE_FILTER_UNTIL" ]]; then
    docker image prune -af --filter "until=$PRUNE_FILTER_UNTIL" || true
  else
    if [[ "$PRUNE_VOLUMES" == true ]]; then
      docker system prune -af --volumes || true
    else
      docker system prune -af || true
    fi
  fi
fi

# Resumen + correo
end_ts=$(date +%s)
elapsed=$(( end_ts - start_ts ))

declare -A display_name_counts=()
for _key in "${!project_display_names[@]}"; do
  _name="${project_display_names[$_key]}"
  (( display_name_counts[$_name]++ ))
done
unset _key _name

format_project_label() {
  local key="$1"
  local name="${project_display_names[$key]:-$key}"
  local hash="${project_hashes[$key]:-}"
  local count="${display_name_counts[$name]:-0}"

  if (( count > 1 )) && [[ -n "$hash" ]]; then
    printf '%s (%s)' "$name" "$hash"
  else
    printf '%s' "$name"
  fi
}

changed_project_labels=()
for key in "${changed_projects[@]}"; do
  [[ -z "$key" ]] && continue
  changed_project_labels+=("$(format_project_label "$key")")
done

failed_project_labels=()
for key in "${failed_projects[@]}"; do
  [[ -z "$key" ]] && continue
  failed_project_labels+=("$(format_project_label "$key")")
done

changed_display="${changed_project_labels[*]:-(ninguno)}"
failed_display="${failed_project_labels[*]:-(ninguno)}"
changed_display_html=$(html_escape "$changed_display")
failed_display_html=$(html_escape "$failed_display")

changed_count=${#changed_projects[@]}
failed_count=${#failed_projects[@]}
changed_count_html=$(html_escape "$changed_count")
failed_count_html=$(html_escape "$failed_count")

elapsed_display="${elapsed}s"
elapsed_display_html=$(html_escape "$elapsed_display")
host_name="$(hostname)"
host_name_html=$(html_escape "$host_name")

subject="$SUBJECT_PREFIX ${changed_count} cambiados, ${failed_count} fallidos"

plain_summary=$(cat <<PLAIN
Docker Compose Updater v2

Proyectos cambiados (${changed_count}): ${changed_display}
Proyectos con errores (${failed_count}): ${failed_display}
Duración: ${elapsed_display}
Host: ${host_name}
PLAIN
)

html_summary=$(cat <<HTML
<!doctype html>
<html><body>
<h3>Docker Compose Updater v2</h3>
<p><b>Cambiados (${changed_count_html}):</b> ${changed_display_html}</p>
<p><b>Errores (${failed_count_html}):</b> ${failed_display_html}</p>
<p><b>Duración:</b> ${elapsed_display_html}<br>
<b>Host:</b> ${host_name_html}</p>
</body></html>
HTML
)

# Adjuntos según política
attachments=()
attached_projects=()
case "$ATTACH_LOGS_ON" in
  always)
    attachments=("${proj_logs[@]}")
    attached_projects=("${project_order[@]}")
    ;;
  changes)
    if (( changed_count > 0 || failed_count > 0 )); then
      declare -A _seen_projects=()
      for name in "${changed_projects[@]}" "${failed_projects[@]}"; do
        [[ -z "${name:-}" ]] && continue
        [[ -n "${_seen_projects[$name]:-}" ]] && continue
        log_path="${project_logs[$name]:-}"
        [[ -z "$log_path" ]] && continue
        attachments+=("$log_path")
        attached_projects+=("$name")
        _seen_projects[$name]=1
      done
      unset _seen_projects
    fi
    ;;
  never) : ;;
  *) : ;;
esac

if (( ${#attachments[@]} == 0 )); then
  attachments_plain="Adjuntos: ninguno"
  attachments_html="<p><b>Adjuntos:</b> ninguno</p>"
else
  attached_project_labels=()
  for key in "${attached_projects[@]}"; do
    [[ -z "$key" ]] && continue
    attached_project_labels+=("$(format_project_label "$key")")
  done
  attachments_plain="Adjuntos (${#attachments[@]}): ${attached_project_labels[*]}"
  attached_project_labels_joined="${attached_project_labels[*]}"
  attachments_count_html=$(html_escape "${#attachments[@]}")
  attached_project_labels_html=$(html_escape "$attached_project_labels_joined")
  attachments_html="<p><b>Adjuntos (${attachments_count_html}):</b> ${attached_project_labels_html}</p>"
fi

plain_summary_with_attachments="$plain_summary"
plain_summary_with_attachments+=$'\n'
plain_summary_with_attachments+="$attachments_plain"

html_summary_with_attachments="${html_summary//<\/body><\/html>/${attachments_html}</body></html>}"

send_email "$subject" "$plain_summary_with_attachments" "$html_summary_with_attachments" "${attachments[@]}"

# Salida final
if (( failed_count > 0 )); then
  exit 2
fi

exit 0
