def resolve(file_settings, environ, overrides):
    for mapping, key in [(overrides, 'limit'), (environ, 'APP_LIMIT'), (file_settings, 'limit')]:
        if key not in mapping:
            continue
        value = mapping[key]
        if mapping is environ and value == '':
            continue
        return 24 if value is None else int(value)
    return 24
