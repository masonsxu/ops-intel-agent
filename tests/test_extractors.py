from ops_intel_agent.extractors import parse_log


def test_extracts_exception_type_and_message():
    raw = (
        "ERROR service=auth host=app-01 JedisConnectionException: "
        "Failed connecting to redis://10.0.1.2:6379 Connection refused"
    )
    ex = parse_log(raw)
    assert ex.exception_type == "JedisConnectionException"
    assert ex.service == "auth"
    assert ex.server_ip == "10.0.1.2"
    assert "JedisConnectionException" in ex.canonical_text
    assert ex.severity == "ERROR"


def test_extracts_java_stack_trace():
    raw = (
        "ERROR java.lang.OutOfMemoryError: Java heap space\n"
        "    at com.example.gateway.router.RequestRouter.dispatch(RequestRouter.java:88)\n"
        "    at java.base/java.util.concurrent.ThreadPoolExecutor.runWorker(ThreadPoolExecutor.java:1128)"
    )
    ex = parse_log(raw)
    assert ex.exception_type == "OutOfMemoryError"
    assert ex.stack_trace is not None
    assert "RequestRouter.dispatch" in ex.stack_trace


def test_canonical_text_handles_bare_message():
    ex = parse_log("something weird happened")
    assert ex.canonical_text
