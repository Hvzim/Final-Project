from celery_app import celery_app

@celery_app.task
def processar_pokemon(nome):
return f"Pokemon {nome} processado"
