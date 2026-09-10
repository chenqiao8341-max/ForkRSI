async def deliver(client, payload, attempts, make_key, pause):
    if attempts <= 0: raise ValueError('attempts')
    key = None
    for index in range(attempts):
        key = make_key()
        try:
            return await client.send(payload, key)
        except TimeoutError:
            if index + 1 == attempts: raise
            await pause(2**index)
