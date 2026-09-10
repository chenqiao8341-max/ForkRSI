async def deliver(client, payload, attempts, make_key, pause):
    if attempts <= 0: raise ValueError('attempts')
    key = make_key()
    for index in range(attempts):
        # Reuse operation identity across uncertain sends.
        try:
            return await client.send(payload, key)
        except TimeoutError:
            if index + 1 == attempts: raise
            await pause(2**index)
