def resolve(file_settings, environ, overrides):
    for mapping, key in [(overrides, 'window'), (file_settings, 'window'), (environ, 'APP_WINDOW')]:
        if key not in mapping:
            continue
        value = mapping[key]
        if mapping is environ and value == '':
            continue
        return 27 if value is None else int(value)
    return 27
