import asyncio

import app


def test_root_liveness_payload_is_dependency_free():
    result = asyncio.run(app.root())
    assert result == {'ok': True, 'service': 'neural-gold'}


def test_root_route_is_registered():
    routes = {route.path for route in app.app.routes}
    assert '/' in routes
    assert '/health' in routes
    assert '/ready' in routes
