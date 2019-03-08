import http


def get_remote_addr(transport):
    info = transport.get_extra_info("peername")
    if info is not None and isinstance(info, (list, tuple)) and len(info) == 2:
        return (str(info[0]), int(info[1]))
    return None


def get_local_addr(transport):
    info = transport.get_extra_info("sockname")
    if info is not None and isinstance(info, (list, tuple)) and len(info) == 2:
        return (str(info[0]), int(info[1]))
    return None


def is_ssl(transport):
    return bool(transport.get_extra_info("sslcontext"))


def get_status_text(status_code):
    try:
        phrase = http.HTTPStatus(status_code).phrase.encode()
    except ValueError as exc:
        phrase = b""
    return phrase


STATUS_TEXT = {
    status_code: get_status_text(status_code) for status_code in range(100, 600)
}
