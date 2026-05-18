import sys
content = open('/hummingbot-api/services/docker_service.py').read()
old = '        environment = {}\n        password = settings.security.config_password\n        if password:\n            environment["CONFIG_PASSWORD"] = password'
new = '''        environment = {
            "PATH": "/opt/conda/envs/hummingbot/bin:/opt/conda/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
            "CONDA_DEFAULT_ENV": "hummingbot",
        }
        password = settings.security.config_password
        if password:
            environment["CONFIG_PASSWORD"] = password'''
if old in content:
    content = content.replace(old, new, 1)
    open('/hummingbot-api/services/docker_service.py', 'w').write(content)
    print('PATCHED OK')
    sys.exit(0)
else:
    print('Pattern not found')
    print(repr(content[content.find('environment = {}'):content.find('environment = {}')+200]))
    sys.exit(1)
