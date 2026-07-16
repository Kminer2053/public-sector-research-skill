#!/bin/sh

set -eu

fail() {
    echo "PSR gateway configuration is invalid" >&2
    exit 1
}

validate_dns_name() {
    value=$1
    [ -n "$value" ] || fail
    [ "${#value}" -le 253 ] || fail
    case "$value" in
        *[!A-Za-z0-9.-]* | .* | *. | *..*)
            fail
            ;;
    esac
    old_ifs=$IFS
    IFS=.
    set -- $value
    IFS=$old_ifs
    for label do
        [ -n "$label" ] || fail
        [ "${#label}" -le 63 ] || fail
        case "$label" in
            -* | *-)
                fail
                ;;
        esac
    done
}

validate_dns_name "${PSR_PUBLIC_HOST:-}"
case "$PSR_PUBLIC_HOST" in
    *.*)
        ;;
    *)
        fail
        ;;
esac
case "$PSR_PUBLIC_HOST" in
    *[!0-9.]*)
        ;;
    *)
        fail
        ;;
esac

validate_dns_name "${PSR_UPSTREAM_HOST:-}"

port=${PSR_UPSTREAM_PORT:-}
case "$port" in
    "" | *[!0-9]*)
        fail
        ;;
esac
[ "${#port}" -le 5 ] || fail
[ "$port" -ge 1 ] || fail
[ "$port" -le 65535 ] || fail

[ -r /etc/nginx/tls/tls.crt ] || fail
[ -r /etc/nginx/tls/tls.key ] || fail

[ "${NGINX_ENVSUBST_FILTER:-}" = "^(PSR_)" ] || fail
[ "${NGINX_ENVSUBST_OUTPUT_DIR:-}" = "/tmp/conf.d" ] || fail
mkdir -p /tmp/conf.d || fail
[ -w /tmp/conf.d ] || fail
