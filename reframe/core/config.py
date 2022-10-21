# Copyright 2016-2022 Swiss National Supercomputing Centre (CSCS/ETH Zurich)
# ReFrame Project Developers. See the top-level LICENSE file for details.
#
# SPDX-License-Identifier: BSD-3-Clause

import copy
import fnmatch
import functools
import itertools
import json
import jsonschema
import os
import re
import socket

import reframe
import reframe.core.settings as settings
import reframe.utility as util
from reframe.core.environments import normalize_module_list
from reframe.core.exceptions import ConfigError, ReframeFatalError
from reframe.core.logging import getlogger
from reframe.utility import ScopedDict


def _match_option(opt, opt_map):
    if isinstance(opt, list):
        opt = '/'.join(opt)

    if opt in opt_map:
        return opt_map[opt]

    for k, v in opt_map.items():
        if fnmatch.fnmatchcase(opt, k):
            return v

    raise KeyError(opt)


def _normalize_syntax(conv):
    '''Normalize syntax for options accepting multiple syntaxes'''

    def _do_normalize(fn):

        @functools.wraps(fn)
        def _get(site_config, option, *args, **kwargs):
            ret = fn(site_config, option, *args, **kwargs)
            if option is None:
                return ret

            for opt_patt, norm_fn in conv.items():
                if re.match(opt_patt, option):
                    ret = norm_fn(ret)
                    break

            return ret

        return _get

    return _do_normalize


def _hostname(use_fqdn, use_xthostname):
    '''Return hostname'''
    if use_xthostname:
        try:
            xthostname_file = '/etc/xthostname'
            getlogger().debug(f'Trying {xthostname_file!r}...')
            with open(xthostname_file) as fp:
                return fp.read()
        except OSError as e:
            '''Log the error and continue to the next method'''
            getlogger().debug(f'Failed to read {xthostname_file!r}')

    if use_fqdn:
        getlogger().debug('Using FQDN...')
        return socket.getfqdn()

    getlogger().debug('Using standard hostname...')
    return socket.gethostname()


class _SiteConfig:
    def __init__(self):
        self._site_config = None
        self._sources = []
        self._subconfigs = {}
        self._local_system = None
        self._sticky_options = {}
        self._autodetect_meth = 'hostname'
        self._autodetect_opts = {
            'hostname': {
                'use_fqdn': False,
                'use_xthostname': False,
            }
        }

        # Open and store the JSON schema for later validation
        schema_filename = os.path.join(reframe.INSTALL_PREFIX, 'reframe',
                                       'schemas', 'config.json')
        with open(schema_filename) as fp:
            try:
                self._schema = json.loads(fp.read())
            except json.JSONDecodeError as e:
                raise ReframeFatalError(
                    f'invalid configuration schema: {schema_filename!r}'
                ) from e

    def update_config(self, config, filename):
        self._sources.append(filename)
        nc = copy.deepcopy(config)
        if self._site_config is None:
            self._site_config = nc
            return self

        for sec in nc.keys():
            if sec not in self._site_config:
                self._site_config[sec] = nc[sec]
            elif sec == 'systems':
                # Systems have to be inserted in the beginning of the list,
                # since they are selected by the first matching entry in
                # `hostnames`.
                self._site_config[sec] = nc[sec] + self._site_config[sec]
            else:
                self._site_config[sec] += nc[sec]

    def _pick_config(self):
        if self._local_system:
            return self._subconfigs[self._local_system]
        else:
            return self._site_config

    def __repr__(self):
        return (f'{type(self).__name__}(site_config={self._site_config!r}, '
                f'sources={self._sources!r})')

    def __str__(self):
        return json.dumps(self._pick_config(), indent=2)

    # Delegate everything to either the original config or to the reduced one
    # if a system is selected

    def __iter__(self):
        return iter(self._pick_config())

    def __getitem__(self, key):
        return self._pick_config()[key]

    def __getattr__(self, attr):
        return getattr(self._pick_config(), attr)

    def set_autodetect_meth(self, method, **opts):
        self._autodetect_meth = method
        try:
            self._autodetect_opts[method].update(opts)
        except KeyError:
            raise ConfigError(
                f'unknown auto-detection method: {method!r}'
            ) from None

    @property
    def schema(self):
        '''Configuration schema'''
        return self._schema

    def add_sticky_option(self, option, value):
        self._sticky_options[option] = value

    def remove_sticky_option(self, option):
        self._sticky_options.pop(option, None)

    def is_sticky_option(self, option):
        return option in self._sticky_options

    @_normalize_syntax({'.*/.*modules$': normalize_module_list})
    def get(self, option, default=None):
        '''Retrieve value of option.

        If the option cannot be retrieved, ``default`` will be returned.
        '''

        # Options may not start with a slash
        if not option or option[0] == '/':
            return default

        # Remove trailing /
        if option[-1] == '/':
            option = option[:-1]

        # Convert any indices to integers
        prepared_option = []
        for opt in option.split('/'):
            try:
                opt = int(opt)
            except ValueError:
                pass

            prepared_option.append(opt)

        # Walk through the option path constructing a default key at the same
        # time for looking it up in the defaults or the sticky options
        default_key = []
        value = self._pick_config()
        option_path_invalid = False
        for x in prepared_option:
            if option_path_invalid:
                # Just go through the rest of elements and construct the key
                # trivially
                if not isinstance(x, int) and x[0] != '@':
                    default_key.append(x)

                continue

            if isinstance(x, int) or x[0] == '@':
                # We are in an addressable element; move forward in the path,
                # without adding the component to the default_key
                if isinstance(x, int):
                    # Element addressable by index number
                    try:
                        value = value[x]
                    except IndexError:
                        option_path_invalid = True
                else:
                    # Element addressable by name
                    x, found = x[1:], False
                    for obj in value:
                        if obj['name'] == x:
                            value, found = obj, True
                            break

                    if not found:
                        option_path_invalid = True

                continue

            if 'type' in value:
                default_key.append(value['type'] + '_' + x)
            else:
                default_key.append(x)

            try:
                value = value[x]
            except (IndexError, KeyError, TypeError):
                option_path_invalid = True

        default_key = '/'.join(default_key)
        try:
            # If a sticky option exists, return that value
            return _match_option(default_key, self._sticky_options)
        except KeyError:
            pass

        if option_path_invalid:
            # Try the default and return
            try:
                return _match_option(default_key, self._schema['defaults'])
            except KeyError:
                return default

        return value

    @property
    def sources(self):
        return self._sources

    @property
    def subconfig_system(self):
        return self._local_system

    def load_config_python(self, filename):
        try:
            mod = util.import_module_from_file(filename)
        except ImportError as e:
            # import_module_from_file() may raise an ImportError if the
            # configuration file is under ReFrame's top-level directory
            raise ConfigError(
                f"could not load Python configuration file: '{filename}'"
            ) from e

        if hasattr(mod, 'settings'):
            # Looks like an old style config
            raise ConfigError(
                f"the syntax of the configuration file {filename!r} "
                f"is no longer supported"
            )

        mod = util.import_module_from_file(filename)
        if not hasattr(mod, 'site_configuration'):
            raise ConfigError(
                f"not a valid Python configuration file: '{filename}'"
            )

        self.update_config(mod.site_configuration, filename)

    def load_config_json(self, filename):
        with open(filename) as fp:
            try:
                config = json.loads(fp.read())
            except json.JSONDecodeError as e:
                raise ConfigError(
                    f"invalid JSON syntax in configuration file '{filename}'"
                ) from e

        self.update_config(config, filename)

    def _detect_system(self):
        getlogger().debug(
            f'Detecting system using method: {self._autodetect_meth!r}'
        )
        hostname = _hostname(
            self._autodetect_opts[self._autodetect_meth]['use_fqdn'],
            self._autodetect_opts[self._autodetect_meth]['use_xthostname'],
        )
        getlogger().debug(f'Retrieved hostname: {hostname!r}')
        getlogger().debug(f'Looking for a matching configuration entry')
        for system in self._site_config['systems']:
            for patt in system['hostnames']:
                if re.match(patt, hostname):
                    sysname = system['name']
                    getlogger().debug(
                        f'Configuration found: picking system {sysname!r}'
                    )
                    return sysname

        raise ConfigError(f"could not find a configuration entry "
                          f"for the current system: '{hostname}'")

    def validate(self):
        site_config = self._pick_config()
        try:
            jsonschema.validate(site_config, self._schema)
        except jsonschema.ValidationError as e:
            raise ConfigError(f"could not validate configuration files: "
                              f"'{self._sources}'") from e

        # Make sure that system and partition names are unique
        system_names = set()
        for system in self._site_config['systems']:
            sysname = system['name']
            if sysname in system_names:
                raise ConfigError(f"system '{sysname}' already defined")

            system_names.add(sysname)
            partition_names = set()
            for part in system['partitions']:
                partname = part['name']
                if partname in partition_names:
                    raise ConfigError(
                        f"partition '{partname}' already defined "
                        f"for system '{sysname}'"
                    )

                partition_names.add(partname)

    def select_subconfig(self, system_fullname=None,
                         ignore_resolve_errors=False):
        # First look for the current subconfig in the cache; if not found,
        # generate it and cache it
        system_fullname = system_fullname or self._detect_system()
        getlogger().debug2(f'Selecting subconfig for {system_fullname!r}')

        self._local_system = system_fullname
        if system_fullname in self._subconfigs:
            return self._subconfigs[system_fullname]

        try:
            system_name, part_name = system_fullname.split(':', maxsplit=1)
        except ValueError:
            # system_name does not have a partition
            system_name, part_name = system_fullname, None

        # Start from a fresh copy of the site_config, because we will be
        # modifying it
        site_config = copy.deepcopy(self._site_config)
        local_config = {}
        systems = list(
            filter(lambda x: x['name'] == system_name, site_config['systems'])
        )
        if not systems:
            raise ConfigError(
                f"could not find a configuration entry "
                f"for the requested system: '{system_name}'"
            )

        if part_name is not None:
            # Filter out also partitions
            systems[0]['partitions'] = list(
                filter(lambda x: x['name'] == part_name,
                       systems[0]['partitions'])
            )

        if not systems[0]['partitions']:
            raise ConfigError(
                f"could not find a configuration entry "
                f"for the requested system/partition combination: "
                f"'{system_name}:{part_name}'"
            )

        # Create local configuration for the current or the requested system
        local_config['systems'] = systems
        for name, section in site_config.items():
            if name == 'systems':
                # The systems sections has already been treated
                continue

            # Convert section to a scoped dict that will handle correctly and
            # transparently the system/partition resolution
            scoped_section = ScopedDict()
            for obj in section:
                key = obj.get('name', name)
                target_systems = obj.get(
                    'target_systems',
                    _match_option(f'{name}/target_systems',
                                  self._schema['defaults'])
                )
                for t in target_systems:
                    scoped_section[f'{t}:{key}'] = obj

            unique_keys = set()
            for obj in section:
                key = obj.get('name', name)
                if key in unique_keys:
                    continue

                unique_keys.add(key)
                try:
                    val = scoped_section[f"{system_fullname}:{key}"]
                except KeyError:
                    pass
                else:
                    local_config.setdefault(name, [])
                    local_config[name].append(val)

        required_sections = self._schema['required']
        for name in required_sections:
            if name not in local_config.keys():
                if not ignore_resolve_errors:
                    raise ConfigError(
                        f"section '{name}' not defined "
                        f"for system '{system_fullname}'"
                    )

        # Verify that all environments defined by the system are defined for
        # the current system
        if not ignore_resolve_errors:
            sys_environs = {
                *itertools.chain(*(p['environs']
                                   for p in systems[0]['partitions']))
            }
            found_environs = {
                e['name'] for e in local_config['environments']
            }
            undefined_environs = sys_environs - found_environs
            if undefined_environs:
                env_descr = ', '.join(f"'{e}'" for e in undefined_environs)
                raise ConfigError(
                    f"environments {env_descr} "
                    f"are not defined for '{system_fullname}'"
                )

        self._subconfigs[system_fullname] = local_config


def find_config_files(config_path=None, config_file=None):
    res = []
    if config_path:
        for p in config_path:
            if os.path.exists(p + '/settings.py'):
                res.append(p + '/settings.py')
            elif os.path.exists(p + '/settings.json'):
                res.append(p + '/settings.json')
            else:
                getlogger().debug(f"No 'settings.py' or 'settings.json' "
                                  f"found in {p!r}, path will be ignored")

    if config_file:
        for f in config_file:
            # If the user sets RFM_CONFIG_FILE=:conf1:conf2 the list will
            # include one empty string in the beginning
            if f == '':
                res = []
            elif f.startswith(':'):
                res = [f[1:]]
            else:
                res.append(f)

    return res


def load_config(*filenames):
    ret = _SiteConfig()
    getlogger().debug('Loading the generic configuration')
    ret.update_config(settings.site_configuration, '<builtin>')
    for f in filenames:
        getlogger().debug(f'Loading configuration file: {filenames!r}')
        _, ext = os.path.splitext(f)
        if ext == '.py':
            ret.load_config_python(f)
        elif ext == '.json':
            ret.load_config_json(f)
        else:
            raise ConfigError(f"unknown configuration file type: '{f}'")

    return ret
