import builtins
import click
import json
import operator
import os

from pprint import pprint

import git
import yaml

from .controller_client import ControllerClient
from .helpers.chute import build_chute
from .store import chute_resolve_source
from .util import update_object


def chute_find_field(chute, key, default=Exception):
    """
    Find a field in a chute definition loading from a paradrop.yaml file.
    """
    if key in chute:
        return chute[key]
    elif 'config' in chute and key in chute['config']:
        return chute['config'][key]
    elif isinstance(default, type):
        raise default("{} field not found in chute definition.".format(key))
    else:
        return default


def chute_resolve_source(source, config):
    """
    Resolve the source section from paradrop.yaml to store configuration.

    If git/http, add an appropriate download section to the chute
    configuration. For git repos, we also identify the latest commit and add
    that to the download information. If type is inline, add a dockerfile
    string field to the chute and no download section.
    """
    if 'type' not in source:
        raise Exception("Source type not specified for chute.")

    source_type = source['type']
    if source_type == 'http':
        config['download'] = {
            'url': source['url']
        }

    elif source_type == 'git':
        repo = git.Repo('.')
        config['download'] = {
            'url': source['url'],
            'checkout': str(repo.head.commit)
        }

    elif source_type == 'inline':
        with open('Dockerfile', 'r') as dockerfile:
            config['dockerfile'] = dockerfile.read()

    else:
        raise Exception("Invalid source type {}".format(source_type))


@click.group('chute')
@click.pass_context
def root(ctx):
    """
    Chute development and publishing functions.
    """
    pass


@root.command('add-wifi-ap')
@click.argument('essid')
@click.option('--password', default=None)
@click.option('--force', default=False, is_flag=True)
@click.pass_context
def add_wifi_ap(ctx, essid, password, force):
    """
    Add a WiFi AP to the chute configuration.
    """
    with open('paradrop.yaml', 'r') as source:
        chute = yaml.safe_load(source)

    # Make sure the config.net section exists.
    net = update_object(chute, 'config.net')

    # Only support adding the first Wi-Fi interface for now.
    if 'wifi' in net and not force:
        print("Wi-Fi interface already exists in paradrop.yaml.")
        print("Please edit the file directly to make changes.")
        return

    net['wifi'] = {
        'type': 'wifi',
        'intfName': 'wlan0',
        'dhcp': {
            'lease': '12h',
            'start': 4,
            'limit': 250
        },
        'ssid': essid,
        'options': {
            'isolate': False,
            'hidden': False
        }
    }

    # Minimum password length is part of the standard.
    if password is not None:
        if len(password) < 8:
            print("Wi-Fi password must be at least 8 characters.")
            return
        net['wifi']['key'] = password

    with open('paradrop.yaml', 'w') as output:
        yaml.safe_dump(chute, output, default_flow_style=False)


@root.command('create-version')
@click.pass_context
def create_version(ctx):
    """
    Push a new version of the chute to the store.
    """
    if not os.path.exists("paradrop.yaml"):
        raise Exception("No paradrop.yaml file found in working directory.")

    with open('paradrop.yaml', 'r') as source:
        chute = yaml.safe_load(source)

    name = chute_find_field(chute, 'name')
    source = chute_find_field(chute, 'source')
    config = chute.get('config', {})

    chute_resolve_source(source, config)

    client = ControllerClient()
    result = client.find_chute(name)
    if result is None:
        raise Exception("Could not find ID for chute {} - is it registered?".format(name))

    result = client.create_version(name, config)
    pprint(result)


@root.command('describe')
@click.argument('name')
@click.pass_context
def describe(ctx, name):
    """
    Show detailed information about a chute in the store.
    """
    client = ControllerClient()
    result = client.find_chute(name)
    pprint(result)


@root.command('export-configuration')
@click.option('--format', '-f', help="Format (json or yaml)")
@click.pass_context
def export_configuration(ctx, format):
    """
    Export chute configuration in JSON or YAML format.

    The configuration format used by the cloud API is slightly different
    from the paradrop.yaml file. This command can export a JSON object in
    a form suitable for installing the chute through the cloud API.

    The config object will usually be used in an envelope like the following:
    {
      "updateClass": "CHUTE",
      "updateType": "update",
      "config": { config-object }
    }
    """
    with open('paradrop.yaml', 'r') as source:
        chute = yaml.safe_load(source)

    if 'source' not in chute:
        print("Error: source section missing in paradrop.yaml")
        return

    config = chute.get('config', {})

    config['name'] = chute['name']
    config['version'] = chute.get('version', 1)

    chute_resolve_source(chute['source'], config)

    if format == "json":
        print(json.dumps(config, sort_keys=True, indent=2))
    elif format == "yaml":
        print(yaml.safe_dump(config, default_flow_style=False))
    else:
        pprint(config)


@root.command('help')
@click.pass_context
def help(ctx):
    """
    Show this message and exit
    """
    click.echo(ctx.parent.get_help())


@root.command('initialize')
@click.pass_context
def initialize(ctx):
    """
    Interactively create a paradrop.yaml file.
    """
    chute = build_chute()
    with open("paradrop.yaml", "w") as output:
        yaml.safe_dump(chute, output, default_flow_style=False)

    # If this is a node.js chute, generate a package.json file from the
    # information that the user provided.
    if chute.get('use', None) == 'node':
        if not os.path.isfile('package.json'):
            data = {
                'name': chute['name'],
                'version': '1.0.0',
                'description': chute['description']
            }
            with open('package.json', 'w') as output:
                json.dump(data, output, sort_keys=True, indent=2)


@root.command('list-chutes')
@click.pass_context
def list_chutes(ctx):
    """
    List chutes in the store that you own or have access to.
    """
    client = ControllerClient()
    result = client.list_chutes()
    click.echo("Name                             Ver Description")
    for chute in sorted(result, key=operator.itemgetter('name')):
        click.echo("{name:32s} {current_version:3d} {description}".format(**chute))


@root.command('list-versions')
@click.argument('name')
@click.pass_context
def list_versions(ctx, name):
    """
    List versions of a chute in the store.
    """
    client = ControllerClient()
    result = client.list_versions(name)
    click.echo("Version GitCheckout")
    for version in sorted(result, key=operator.itemgetter('version')):
        try:
            code = version['config']['download']['checkout']
        except:
            code = "N/A"
        print("{:7s} {}".format(str(version['version']), code))


@root.command()
@click.pass_context
@click.option('--public/--not-public', default=False)
def register(ctx, public):
    """
    Register a chute with the store.
    """
    if not os.path.exists("paradrop.yaml"):
        raise Exception("No paradrop.yaml file found in working directory.")

    with open('paradrop.yaml', 'r') as source:
        chute = yaml.safe_load(source)

    name = chute_find_field(chute, 'name')
    description = chute_find_field(chute, 'description')

    print("Name: {}".format(name))
    print("Description: {}".format(description))
    print("Public: {}".format(public))
    print("")

    prompt = "Ready to send this information to {} (Y/N)? ".format(
            ctx.obj['pdserver_url'])
    response = builtins.input(prompt)
    print("")

    if response.upper().startswith("Y"):
        client = ControllerClient()
        result = client.create_chute(name, description, public=public)
        pprint(result)
    else:
        print("Operation cancelled.")


@root.command('set')
@click.argument('path')
@click.argument('value')
@click.pass_context
def set_config(ctx, path, value):
    """
    Set a value in the paradrop.yaml file.

    Example: set config.web.port 80
    """
    with open('paradrop.yaml', 'r') as source:
        chute = yaml.safe_load(source)

    # Calling yaml.safe_load on the value does a little type interpretation
    # (e.g. numeric vs. string) and allows the user to directly set lists and
    # other structures.
    value = yaml.safe_load(value)

    def set_value(parent, key, created):
        if created:
            print("Creating new field {} = {}".format(path, value))
        else:
            current = parent[key]
            print("Changing {} from {} to {}".format(path, current, value))

        parent[key] = value

    update_object(chute, path, set_value)

    with open('paradrop.yaml', 'w') as output:
        yaml.safe_dump(chute, output, default_flow_style=False)
