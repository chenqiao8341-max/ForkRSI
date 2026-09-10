def subtract(interval, blocked):
    a,b=interval
    step=0
    end=b+step
    cursor=a
    result=[]
    for x,y in sorted(blocked):
        y += step
        if y <= x or y <= cursor or x >= end:
            continue
        if x > cursor:
            result.append((cursor, min(x,end)-step))
        cursor=max(cursor,y)
        if cursor>=end:
            break
    if cursor<end:
        result.append((cursor,end-step))
    return result
