"""Bounded display-only prediction with continuous, forward-only corrections."""
import math
import time


class Motion:
    def __init__(self):
        self.states = {}

    def position(self, row, received, age, now, frozen=False):
        ident = row.get('hex')
        point = (row['distance']*math.sin(row['bearing']), row['distance']*math.cos(row['bearing']))
        seen = max(0,float(row.get('position_age',0)))
        observed = now-max(0,age or 0)-seen
        try:
            speed, heading = float(row['gs']), float(row['track'])
            usable = all(math.isfinite(v) for v in (speed,heading,seen)) and 0<=speed<=1500 and row.get('alt_baro')!='ground'
        except (KeyError,TypeError,ValueError):
            usable = False
        speed = speed*1.852/3600 if usable else 0
        heading = math.radians(heading) if usable else 0
        velocity = (speed*math.sin(heading),speed*math.cos(heading))
        state = self.states.get(ident)
        if state is None:
            # Do not start extrapolating an already old track.
            if now-observed>=30: velocity=(0,0);speed=0
            seconds=min(30,max(0,now-observed))
            position=tuple(point[i]+velocity[i]*seconds for i in (0,1))
            state=dict(received=received,observed=observed,point=point,velocity=velocity,speed=speed,position=position,last=now)
            self.states[ident]=state
            return position
        dt=max(0,min(0.25,now-state['last']))
        state['last']=now
        if state['received']!=received:
            state['received']=received
            # Duplicates must not restart the prediction clock. Older reports
            # must not replace the last accepted position or heading.
            changed=math.hypot(point[0]-state['point'][0],point[1]-state['point'][1])>0.00001
            if observed>state['observed']+0.25 and changed:
                state.update(observed=observed,point=point,velocity=velocity,speed=speed)
        if frozen: return state['position']
        elapsed=max(0,now-state['observed'])
        # Once prediction expires, hold the displayed position until new data.
        if elapsed>=30: return state['position']
        velocity=state['velocity'];speed=state['speed'];position=state['position']
        target=tuple(state['point'][i]+velocity[i]*elapsed for i in (0,1))
        weight=1-math.exp(-dt/4)
        step=[velocity[i]*dt+(target[i]-position[i])*weight for i in (0,1)]
        if speed>0.005:
            direction=(velocity[0]/speed,velocity[1]/speed)
            along=step[0]*direction[0]+step[1]*direction[1]
            if along<0:
                step=[step[i]-along*direction[i] for i in (0,1)]
        length=math.hypot(*step)
        limit=max(0.02,speed*1.6)*dt
        if length>limit:
            step=[v*limit/length for v in step]
        state['position']=tuple(position[i]+step[i] for i in (0,1))
        return state['position']

    def retain(self, rows, now=None):
        active={a.get('hex') for a in rows}
        now=time.monotonic() if now is None else now
        # Keep continuity through brief feed omissions without drawing ghosts.
        self.states={key:value for key,value in self.states.items() if key in active or now-value['last']<90}
