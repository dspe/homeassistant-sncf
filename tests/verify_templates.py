"""Régressions hors ligne pour les modèles YAML réellement distribués."""
import ast
from pathlib import Path
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import yaml
from jinja2.sandbox import SandboxedEnvironment
from jinja2 import StrictUndefined
class Loader(yaml.SafeLoader): pass
Loader.add_constructor('!secret', lambda l,n: l.construct_scalar(n))
root=Path(__file__).resolve().parents[1]
pkg=yaml.load((root/'packages/sncf_epernon.yaml').read_text(), Loader=Loader)
card=yaml.safe_load((root/'dashboards/carte.yaml').read_text())
env=SandboxedEnvironment(undefined=StrictUndefined)
clock=datetime(2026,10,23,7,0,tzinfo=ZoneInfo('Europe/Paris'))
raw={}
raw_states={}
def stamp(value, default=0):
    try: return datetime.fromisoformat(value).timestamp() if isinstance(value,str) else value.timestamp()
    except (ValueError,TypeError,AttributeError): return default
def parse(value, fmt, default=None):
    try: return datetime.strptime(value,fmt)
    except (ValueError,TypeError): return default
env.globals.update(now=lambda: clock, timedelta=timedelta, strptime=parse, as_timestamp=stamp,
    states=lambda name: raw_states.get(name,'unknown'),
    state_attr=lambda name,key: raw.get(name,{}).get(key))
code=pkg['template'][0]['sensor'][0]
template=env.from_string(code['attributes']['trains'])
pre='sensor.sncf_epernon_prevu'; live='sensor.sncf_epernon_temps_reel'
def departure(t='070500',base=None,number='862406',fresh='realtime',direction='Paris - Montparnasse - Hall 1 & 2',alerts=()):
    d={'display_informations':{'headsign':number,'physical_mode':'Train régional ou Intercités','direction':direction,'links':[{'type':'disruption','id':x} for x in alerts]},'stop_date_time':{'departure_date_time':'20261023T'+t,'base_departure_date_time':'20261023T'+(base or t)},'stop_point':{'id':'stop_point:epernon'}}
    if fresh is not None: d['stop_date_time']['data_freshness']=fresh
    return d
def impact(effect='NO_SERVICE',ident='c',start='20261023T060000',end='20261023T100000',stops=None):
    return {'id':ident,'severity':{'effect':effect},'application_periods':[{'begin':start,'end':end}],'impacted_objects':[{'impacted_stops':stops or []}]}
def render(p=(),r=(),imp=()):
    raw.clear();raw.update({pre:{'departures':list(p),'disruptions':list(imp)},live:{'departures':list(r),'disruptions':[]}})
    raw_states.update({pre:clock.isoformat(),live:clock.isoformat()})
    return ast.literal_eval(template.render().strip())
checks=0
def check(condition,label):
    global checks
    assert condition,label
    checks+=1
p=departure(fresh='base_schedule');r=departure()
rows=render([p],[r]);check(len(rows)==1 and rows[0]['statut']=='🟢 À l’heure','on time and deduplicated')
rows=render([p],[departure(fresh='base_schedule')]);check(rows[0]['statut']=='⚪ Horaire prévu','planned only is never green')
rows=render([p],[]);check(not rows[0]['supprime'],'absent realtime is not cancelled')
rows=render([departure(alerts=['c'])],[],[impact()]);check(rows[0]['supprime'],'explicit cancellation retained')
rows=render([p],[],[impact()]);check(not rows[0]['supprime'],'unlinked disruption does not cancel')
rows=render([departure(alerts=['c'])],[],[impact(start='20261024T060000',end='20261024T100000')]);check(not rows[0]['supprime'],'future disruption does not cancel today')
rows=render([p],[departure(t='071700',base='070500')]);check(rows[0]['statut']=='🟠 +12 min' and rows[0]['estime']=='07:17','delay compared with planned time')
rows=render([departure(t='065000')],[departure(t='071000',base='065000')]);check(len(rows)==1,'delayed train retained after scheduled departure')
rows=render([departure(t='065000',alerts=['c'])],[],[impact()]);check(rows==[],'past cancellation removed')
rows=render([departure(direction='Chartres')],[departure(direction='Chartres')]);check(rows==[],'opposite direction filtered')
rows=render([],[]);check(rows==[],'empty response')
rows=render([], [departure(number='999999')]);check(rows[0]['numero']=='999999','additional realtime train')
rows=render([departure(alerts=['c'])],[],[impact(effect='REDUCED_SERVICE',stops=[{'stop_point':{'id':'stop_point:epernon'},'departure_status':'deleted'}])]);check(rows[0]['supprime'],'departure stop deleted')
rows=render([departure(alerts=['c'])],[],[impact(effect='REDUCED_SERVICE',stops=[{'stop_point':{'id':'stop_point:other'},'departure_status':'deleted'}])]);check(not rows[0]['supprime'] and rows[0]['statut']=='🟠 Perturbation','other stop deletion not full cancellation')
i=impact();i['application_patterns']=[{'week_pattern':{'monday':True}}]
rows=render([departure(alerts=['c'])],[],[i]);check(not rows[0]['supprime'] and rows[0]['statut']=='⚪ Horaire prévu','incomplete calendar does not cancel')
i=impact();i['application_patterns']=[{'application_period':{'begin':'20261023','end':'20261023'},'week_pattern':{'friday':True},'time_slots':[{'begin':'070000','end':'080000'}]}]
rows=render([departure(alerts=['c'])],[],[i]);check(rows[0]['supprime'],'matching calendar cancels')
i['application_patterns'][0]['week_pattern']={'monday':True}
rows=render([departure(alerts=['c'])],[],[i]);check(not rows[0]['supprime'],'wrong weekday does not cancel')
i['application_patterns']=[{'application_period':{'begin':'20261022','end':'20261022'},'week_pattern':{'thursday':True},'time_slots':[{'begin':'230000','end':'080000'}]}]
rows=render([departure(alerts=['c'])],[],[i]);check(rows[0]['supprime'],'overnight slot applies after midnight')
rows=render([p],[departure(fresh=None)]);check(rows[0]['statut']=='⚪ Horaire prévu','missing freshness flag')
x=departure(fresh=None);x['stop_date_time']['stop_date_time']='realtime'
rows=render([p],[x]);check(rows[0]['statut']=='🟢 À l’heure','legacy freshness field')
rows=render([departure(t='070500')],[departure(t='070300',base='070500')]);check(rows[0]['statut']=='🟠 En avance','early departure')
rows=render([departure(t=f'{h:02}0500',number=str(h)) for h in range(8,16)]);check(len(rows)==5 and rows[0]['numero']=='8','five earliest departures')
x=departure();x['stop_date_time']['departure_date_time']='20261024T060100';x['stop_date_time']['base_departure_date_time']='20261024T060100'
rows=render([x]);check(rows[0]['prevu']=='24/10 06:01','tomorrow includes date')
render()
check(env.from_string(code['availability']).render().strip()=='True','fresh response available')
raw_states[pre]=(clock-timedelta(minutes=4)).isoformat()
check(env.from_string(code['availability']).render().strip()=='False','stale response unavailable')
raw_states[pre]='unavailable'
check(env.from_string(code['availability']).render().strip()=='False','failed response unavailable')
for endpoint in pkg['rest']:
    s=endpoint['sensor'][0]
    check(env.from_string(s['value_template']).render(value_json={'departures':[]}).strip()==clock.isoformat(),'success receives timestamp')
    check(env.from_string(s['value_template']).render(value_json={'error':{'id':'bad'}}).strip()=='None','API error not success')
    check('T040000' in env.from_string(endpoint['params']['from_datetime']).render(),'lookbehind query')
print(f'{checks} vérifications réussies ; fichiers YAML et modèles Jinja analysés.')
