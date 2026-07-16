from super_memory import __version__
from super_memory.api import app
from super_memory.mcp_server import SERVER_INFO


def test_api_and_mcp_share_package_version():
    assert app.version == __version__
    assert SERVER_INFO == {"name": "super-memory", "version": __version__}
