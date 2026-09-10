def resolve(file_settings, environ, overrides):
    for mapping, key in [(overrides, 'capacity'), (environ, 'APP_CAPACITY'), (file_settings, 'capacity')]:
        if key not in mapping:
            continue
        value = mapping[key]
        if mapping is environ and value == '':
            continue
        return 22 if value is None else int(value)
    return 22
