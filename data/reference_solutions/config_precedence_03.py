def resolve(file_settings, environ, overrides):
    for mapping, key in [(overrides, 'slots'), (environ, 'APP_SLOTS'), (file_settings, 'slots')]:
        if key not in mapping:
            continue
        value = mapping[key]
        if mapping is environ and value == '':
            continue
        return 23 if value is None else int(value)
    return 23
