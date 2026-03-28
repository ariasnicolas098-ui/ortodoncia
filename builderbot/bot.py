import requests
import json
import os

# Configuración
BACKEND_URL = os.environ.get('BACKEND_URL', 'https://tu-dominio.com')  # Tu URL de Flask
API_KEY = os.environ.get('API_KEY', 'tu-api-key-secreta')

def procesar_mensaje(mensaje, numero):
    """
    Función principal que BuilderBot llama cuando llega un mensaje
    """
    # Enviar mensaje a tu backend Flask
    try:
        response = requests.post(
            f"{BACKEND_URL}/api/whatsapp/webhook",
            json={
                'from': numero,
                'message': mensaje,
                'api_key': API_KEY
            },
            timeout=30
        )
        
        if response.status_code == 200:
            data = response.json()
            return data.get('response', 'Lo siento, hubo un error procesando tu mensaje')
        else:
            return "Lo siento, el sistema está ocupado. Intenta más tarde."
            
    except Exception as e:
        print(f"Error: {e}")
        return "Error de conexión. Por favor intenta más tarde."


# Configuración para BuilderBot Cloud
CONFIG = {
    'name': 'Consultorio Dental Bot',
    'description': 'Bot para gestión de citas y consultas dentales',
    'webhook_url': '/webhook',  # BuilderBot llamará a esta función
    'auto_reply': True
}