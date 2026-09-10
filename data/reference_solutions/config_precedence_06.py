def resolve(file_settings, environ, overrides):
    for mapping, key in [(overrides, 'batch'), (file_settings, 'batch'), (environ, 'APP_BATCH')]:
        if key not in mapping:
            continue
        value = mapping[key]
        if mapping is environ and value == '':
            continue
        return 26 if value is None else int(value)
    return 26
