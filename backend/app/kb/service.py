from copy import deepcopy


SECTIONS = {'SC03':'products.casco', 'SC09':'products.dms', 'SC11':'claims.road_accident_now',
            'SC18':'claims.documents', 'SC24':'products.dms.e_card', 'SC31':'payments',
            'SC32':'bonus_malus', 'SC34':'app_help', 'SC38':'fraud_policy', 'SC40':'products'}


class KnowledgeBase:
    def __init__(self, dataset):
        self.data = dataset.documents['knowledge_base.json']

    def lookup(self, topic):
        value = self.data
        try:
            for part in topic.split('.'):
                value = value[int(part)] if isinstance(value, list) else value[part]
        except (KeyError, IndexError, ValueError, TypeError):
            raise ValueError('not_found')
        return {'source_id': 'knowledge_base.json#/' + topic.replace('.', '/'), 'value': deepcopy(value)}

    def for_scenario(self, scenario, values):
        topic = SECTIONS.get(scenario)
        if scenario == 'SC07': topic = 'products.property'
        if scenario == 'SC08': topic = 'products.accident'
        if scenario == 'SC18' and values.get('product_type') in self.data['claims']['documents']:
            topic += '.' + values['product_type']
        if scenario == 'SC40' and values.get('product_type'):
            topic += '.' + values['product_type']
        return self.lookup(topic or 'company')
