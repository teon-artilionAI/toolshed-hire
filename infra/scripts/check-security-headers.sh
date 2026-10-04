#!/usr/bin/env bash
#
# Check the security headers and the TLS floor of a deployed environment.
#
# The headers are set in two places, frontend/vercel.json for every response
# the browser receives and app/api/security_headers.py for the API. A change to
# either, or to Vercel's own defaults, could drop one without any test noticing,
# because the tests run against vite preview and a local API. This runs against
# the real domain after every deployment, so a missing header fails the
# deployment instead of going unseen.
#
# What is checked, on the page the browser loads and on an API response that
# passes through the /api rewrite:
#   Strict-Transport-Security with a max-age of at least half a year
#   Content-Security-Policy with default-src 'none' and frame-ancestors 'none'
#   X-Content-Type-Options: nosniff
#   Referrer-Policy and Permissions-Policy present
# And on the connection:
#   plain http redirects to https
#   TLS 1.1 and older are refused
#
# Required environment:
#   SITE_URL   Origin of the deployed frontend, no trailing slash
#
# Optional environment:
#   API_PATH                    default /api/health
#   HEADER_CHECK_TIMEOUT_SECONDS default 20

set -uo pipefail

: "${SITE_URL:?SITE_URL is not set. There is nothing to check.}"

API_PATH="${API_PATH:-/api/health}"
HEADER_CHECK_TIMEOUT_SECONDS="${HEADER_CHECK_TIMEOUT_SECONDS:-20}"
# Half a year, the max-age NFR-07 asks for and the site sends.
HSTS_MINIMUM_SECONDS=15768000

failures=0

fail() {
  echo "::error title=Security header check::$1"
  failures=$((failures + 1))
}

pass() {
  echo "ok    $1"
}

# Prints the response headers of a GET, one per line, names in lower case.
headers_of() {
  curl --silent --show-error --max-time "${HEADER_CHECK_TIMEOUT_SECONDS}" \
    --dump-header - --output /dev/null "$1" \
    | tr -d '\r' | awk -F': ' 'NF > 1 { printf "%s: %s\n", tolower($1), substr($0, index($0, ": ") + 2) }'
}

check_headers() {
  local url="$1"
  local found
  if ! found="$(headers_of "${url}")" || [ -z "${found}" ]; then
    fail "${url} did not answer"
    return
  fi

  local hsts
  hsts="$(printf '%s\n' "${found}" | awk -F': ' '$1 == "strict-transport-security" { print $2 }')"
  local max_age
  max_age="$(printf '%s' "${hsts}" | sed -n 's/.*max-age=\([0-9]*\).*/\1/p')"
  if [ -n "${max_age}" ] && [ "${max_age}" -ge "${HSTS_MINIMUM_SECONDS}" ]; then
    pass "${url} Strict-Transport-Security max-age=${max_age}"
  else
    fail "${url} has no Strict-Transport-Security of at least ${HSTS_MINIMUM_SECONDS} seconds (got '${hsts}')"
  fi

  local csp
  csp="$(printf '%s\n' "${found}" | awk -F': ' '$1 == "content-security-policy" { print $2 }')"
  if [[ "${csp}" == *"default-src 'none'"* && "${csp}" == *"frame-ancestors 'none'"* ]]; then
    pass "${url} Content-Security-Policy denies by default and refuses framing"
  else
    fail "${url} Content-Security-Policy is missing default-src 'none' or frame-ancestors 'none' (got '${csp}')"
  fi

  if printf '%s\n' "${found}" | grep -qx "x-content-type-options: nosniff"; then
    pass "${url} X-Content-Type-Options nosniff"
  else
    fail "${url} has no X-Content-Type-Options: nosniff"
  fi

  local name
  for name in referrer-policy permissions-policy; do
    if printf '%s\n' "${found}" | grep -q "^${name}: "; then
      pass "${url} ${name}"
    else
      fail "${url} has no ${name} header"
    fi
  done
}

check_redirect_to_https() {
  local plain="http://${SITE_URL#https://}/"
  local location
  location="$(curl --silent --max-time "${HEADER_CHECK_TIMEOUT_SECONDS}" --dump-header - --output /dev/null "${plain}" \
    | tr -d '\r' | awk -F': ' 'tolower($1) == "location" { print $2 }')"
  if [[ "${location}" == https://* ]]; then
    pass "${plain} redirects to https"
  else
    fail "${plain} does not redirect to https (Location '${location}')"
  fi
}

# The probe uses openssl s_client with the client's own floor lowered, because a
# modern client refuses TLS 1.1 by itself and would make a refusal look like
# the server's doing. The negotiated protocol is read from the line that starts
# with "New,", which says "(NONE)" when the handshake failed. The "Protocol"
# line further down only repeats the version that was attempted. A TLS 1.2
# handshake to the same host is the control that shows the probe can connect.
handshake_protocol() {
  local host="$1" version_flag="$2"
  echo | timeout "${HEADER_CHECK_TIMEOUT_SECONDS}" openssl s_client -connect "${host}:443" -servername "${host}"     "${version_flag}" -cipher 'DEFAULT@SECLEVEL=0' 2> /dev/null     | awk -F', ' '/^New, / { print $2; exit }'
}

check_old_tls_refused() {
  if ! command -v openssl > /dev/null; then
    fail "openssl is not available, so the TLS floor cannot be checked"
    return
  fi
  local host="${SITE_URL#https://}"
  host="${host%%/*}"
  local modern old
  modern="$(handshake_protocol "${host}" -tls1_2)"
  if [ "${modern}" != "TLSv1.2" ]; then
    fail "${host} did not complete a TLS 1.2 handshake, so the probe proves nothing (got '${modern}')"
    return
  fi
  old="$(handshake_protocol "${host}" -tls1_1)"
  if [ -n "${old}" ] && [ "${old}" != "(NONE)" ]; then
    fail "${host} accepted a ${old} connection"
  else
    pass "${host} completes TLS 1.2 and refuses TLS 1.1"
  fi
}

echo "Checking the security headers and TLS of ${SITE_URL}"
check_headers "${SITE_URL}/"
check_headers "${SITE_URL}${API_PATH}"
check_redirect_to_https
check_old_tls_refused

if [ "${failures}" -gt 0 ]; then
  echo "${failures} security check(s) failed for ${SITE_URL}."
  exit 1
fi
echo "Every security header and TLS check passed for ${SITE_URL}."
