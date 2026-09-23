import re
from copy import deepcopy
from app.router.validator import validate_slot_value
from app.router.schemas import SlotUpdate
from app.state.models import now


class SlotManager:
    def __init__(self, dataset):
        self.dataset = dataset

    def apply(self, state, updates, topic, version):
        changes = []
        for update in updates:
            sid = update.slot_id
            scope = '__identity__' if sid in {'phone', 'iin'} else (update.topic_id or topic)
            if not scope:
                continue
            value = update.normalized_value
            if isinstance(value, str):
                value = value.strip()
                if sid == 'phone':
                    digits = re.sub(r'\D', '', value)
                    value = '+7' + digits[-10:] if len(digits) in {10, 11} else value
                elif sid in {'policy_number', 'claim_number', 'vehicle_plate', 'culprit_vehicle_plate'}:
                    value = value.upper().replace(' ', '')
            validate_slot_value(self.dataset.slots[sid], value)
            target = state['slots_by_topic'].setdefault(scope, {})
            old = target.get(sid)
            if old and old['normalized_value'] == value:
                continue
            record = {**update.model_dump(), 'normalized_value': value, 'topic_id': None if scope == '__identity__' else scope,
                      'timestamp': now(), 'state_version': version, 'superseded_values': []}
            if old:
                record['superseded_values'] = [*old.get('superseded_values', []), {k:v for k,v in old.items() if k != 'superseded_values'}]
            target[sid] = record
            changes.append({'slot_id': sid, 'scope': scope, 'old': deepcopy(old), 'new': deepcopy(record)})
        return changes

    def values(self, state, topic):
        return {k:v['normalized_value'] for group in ('__identity__', topic) for k,v in state['slots_by_topic'].get(group, {}).items() if v['normalized_value'] is not None}

    def router_slots(self, state):
        return [SlotUpdate(**{k:v[k] for k in SlotUpdate.model_fields})
                for group in state['slots_by_topic'].values() for v in group.values()]

    def missing(self, state, topic):
        values = self.values(state, topic)
        return [s for s in self.dataset.scenarios[topic]['slots']['required'] if s not in values]

    def question(self, slot, language):
        return self.dataset.slots.get(slot, self.dataset.slots['phone'])['prompt'][language]
