def resolve(file_settings, environ, overrides):
    for mapping, key in [(overrides, 'budget'), (environ, 'APP_BUDGET'), (file_settings, 'budget')]:
        if key not in mapping:
            continue
        value = mapping[key]
        if mapping is environ and value == '':
            continue
        return 25 if value is None else int(value)
    return 25
