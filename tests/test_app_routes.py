import app


def test_root_route_exists_for_platform_probes():
    routes = {route.path for route in app.app.routes}
    assert '/' in routes
    assert '/health' in routes
    assert '/ready' in routes
