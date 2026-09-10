def resolve(file_settings, environ, overrides):
    for mapping, key in [(overrides, 'quota'), (environ, 'APP_QUOTA'), (file_settings, 'quota')]:
        if key not in mapping:
            continue
        value = mapping[key]
        if mapping is environ and value == '':
            continue
        return 20 if value is None else int(value)
    return 20
