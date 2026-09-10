def resolve(file_settings, environ, overrides):
    for mapping, key in [(overrides, 'workers'), (environ, 'APP_WORKERS'), (file_settings, 'workers')]:
        if key not in mapping:
            continue
        value = mapping[key]
        if mapping is environ and value == '':
            continue
        return 21 if value is None else int(value)
    return 21
