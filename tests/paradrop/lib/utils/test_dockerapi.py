from paradrop.lib.container import dockerapi
from mock import patch, MagicMock
from nose.tools import assert_raises

DOCKER_CONF = """
# Docker systemd configuration
#
# This configuration file was automatically generated by Paradrop.  Any changes
# will be overwritten on startup.

# Tell docker not to start containers automatically on startup.
DOCKER_OPTIONS="--restart=false"
"""

def fake_create_host_config(**kwargs):
    return kwargs


def fake_update():
    class Object(object):
        pass

    update = Object()
    update.new = Object()
    return update


@patch('paradrop.lib.container.dockerapi.getBridgeGateway')
def test_build_host_config(getBridgeGateway):
    """
    Test that the build_host_config function does it's job.
    """
    # We don't want to open an actual Docker client connection to do this unit
    # test, so mock out the create_host_config to return whatever is passed to
    # it.
    client = MagicMock()
    client.create_host_config = fake_create_host_config

    #Check that an empty host_config gives us certain default settings
    chute = MagicMock()
    res = dockerapi.build_host_config(chute, client)
    assert res['network_mode'] == 'bridge'

    #Check that passing things through host_config works
    chute = MagicMock()
    chute.host_config = {'port_bindings': { 80:9000}, 'dns': ['0.0.0.0', '8.8.8.8']}
    res = dockerapi.build_host_config(chute, client)
    assert res['dns'] == ['0.0.0.0', '8.8.8.8']

@patch('paradrop.lib.container.dockerapi.setup_net_interfaces')
@patch('paradrop.lib.container.dockerapi.out')
@patch('docker.Client')
def test_restartChute(mockDocker, mockOutput, mockInterfaces):
    """
    Test that the restartChute function does it's job.
    """
    update = MagicMock()
    update.name = 'test'
    client = MagicMock()
    mockDocker.return_value = client
    dockerapi.restartChute(update)
    mockDocker.assert_called_once_with(base_url='unix://var/run/docker.sock', version='auto')
    mockInterfaces.assert_called_once_with(update.new)
    client.start.assert_called_once_with(container=update.name)

@patch('paradrop.lib.container.dockerapi.out')
@patch('docker.Client')
def test_stopChute(mockDocker, mockOutput):
    """
    Test that the stopChute function does it's job.
    """
    update = MagicMock()
    update.name = 'test'
    client = MagicMock()
    mockDocker.return_value = client
    dockerapi.stopChute(update)
    mockDocker.assert_called_once_with(base_url='unix://var/run/docker.sock', version='auto')
    client.stop.assert_called_once_with(container=update.name)

@patch('paradrop.lib.container.dockerapi.out')
@patch('docker.Client')
def test_removeChute(mockDocker, mockOutput):
    """
    Test that the removeChute function does it's job.
    """
    update = MagicMock()
    update.name = 'test'
    client = MagicMock()
    mockDocker.return_value = client
    dockerapi.removeChute(update)
    mockDocker.assert_called_once_with(base_url='unix://var/run/docker.sock', version='auto')
    client.remove_container.assert_called_once_with(container=update.name, force=True)
    client.remove_image.assert_called_once()
    assert update.complete.call_count == 0
    client.reset_mock()
    client.remove_container.side_effect = Exception('Test')
    try:
        dockerapi.removeChute(update)
    except Exception as e:
        assert e.message == 'Test'
    client.remove_container.assert_called_once_with(container=update.name, force=True)

@patch('paradrop.lib.container.dockerapi.prepare_environment')
@patch('paradrop.lib.container.dockerapi.build_host_config')
@patch('paradrop.lib.container.dockerapi.setup_net_interfaces')
@patch('paradrop.lib.container.dockerapi.out')
@patch('docker.Client')
def test_startChute(mockDocker, mockOutput, mockInterfaces, mockConfig, prepare_environment):
    """
    Test that the startChute function does it's job.
    """
    #Test successful start attempt
    mockConfig.return_value = 'ConfigDict'
    update = MagicMock()
    update.name = 'test'
    update.dockerfile = 'Dockerfile'
    client = MagicMock()
    client.images.return_value = 'images'
    client.containers.return_value = 'containers'
    client.build.return_value = ['{"stream": "test"}','{"value": {"test": "testing"}}','{"tests": "stuff"}']
    client.create_container.return_value = {'Id': 123}
    mockDocker.return_value = client
    prepare_environment.return_value = {}
    dockerapi.startChute(update)
    mockConfig.assert_called_once_with(update.new, client)
    mockDocker.assert_called_once_with(base_url='unix://var/run/docker.sock', version='auto')
    client.create_container.assert_called_once()
    client.start.assert_called_once_with(123)
    mockInterfaces.assert_called_once_with(update.new)

    #Test when create or start throws exceptions
    client.build.return_value = ['{"stream": "test"}','{"value": {"test": "testing"}}','{"tests": "stuff"}']
    client.create_container.side_effect = Exception('create container exception')
    assert_raises(Exception, dockerapi.startChute, update)
    client.start.side_effect = Exception('start exception')
    assert_raises(Exception, dockerapi.startChute, update)

@patch('__builtin__.open')
@patch('paradrop.lib.container.dockerapi.os')
@patch('paradrop.lib.container.dockerapi.out')
def test_writeDockerConfig(mockOutput, mockOS, mock_open):
    """
    Test that the writeDockerConfig function does it's job.
    """
    fd = MagicMock()
    mock_open.return_value = fd
    #Test we get a warning and nothing else if path doesn't exist
    mockOS.path.exists.return_value = False
    dockerapi.writeDockerConfig()
    assert not mock_open.called
    assert len(mockOS.method_calls) == 1

    #Test that it writes if we find path
    mockOS.path.exists.side_effect = [True, False, True]
    mockOS.listdir.return_value = ['/root', '/var']
    dockerapi.writeDockerConfig()
    assert mock_open.call_count == 1
    file_handle = mock_open.return_value.__enter__.return_value
    file_handle.write.assert_called_once_with(DOCKER_CONF)

    #Test that we handle an excpetion when opening
    mockOS.path.exists.side_effect = None
    mockOS.path.exists.return_value = True
    mockOS.listdir.return_value = ['/root']
    mock_open.side_effect = Exception('Blammo!')
    dockerapi.writeDockerConfig()
    assert mock_open.call_count == 2
