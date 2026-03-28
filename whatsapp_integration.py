"""
whatsapp_integration.py
Endpoints que BuilderBot Cloud llamará para procesar mensajes
"""

from flask import Flask, request, jsonify, Blueprint
from database import db
from datetime import datetime
import json
import re

# Crear blueprint para WhatsApp
whatsapp_bp = Blueprint('whatsapp', __name__, url_prefix='/api/whatsapp')

# Estados de conversación
ESTADOS = {
    'NUEVO': 'nuevo',
    'BUSCANDO_PACIENTE': 'buscando_paciente',
    'AGENDANDO_CITA': 'agendando_cita',
    'SELECCIONANDO_FECHA': 'seleccionando_fecha',
    'SELECCIONANDO_HORA': 'seleccionando_hora',
    'CONFIRMANDO_CITA': 'confirmando_cita',
    'VER_CITAS': 'ver_citas',
    'VER_HISTORIAL': 'ver_historial'
}

# Menú principal
MENU_PRINCIPAL = """
🦷 *CONSULTORIO DENTAL*

Selecciona una opción:
1️⃣ Buscar paciente
2️⃣ Agendar cita
3️⃣ Ver mis citas
4️⃣ Ver historial médico
5️⃣ Información de contacto
6️⃣ Cancelar cita

Responde con el *número* de la opción
"""


@whatsapp_bp.route('/webhook', methods=['POST'])
def whatsapp_webhook():
    """
    Endpoint principal que BuilderBot Cloud llamará
    cuando llegue un mensaje de WhatsApp
    """
    data = request.get_json()
    
    # Extraer datos del mensaje
    numero = data.get('from')  # Número de teléfono del remitente
    mensaje = data.get('message', '').strip().lower()
    mensaje_id = data.get('id')
    
    # Guardar mensaje en BD
    db.guardar_mensaje_whatsapp(numero, mensaje, 'recibido')
    
    # Obtener o crear sesión
    sesion = db.obtener_o_crear_sesion(numero)
    estado_actual = sesion['estado']
    
    # Procesar según estado
    respuesta = procesar_mensaje(numero, mensaje, estado_actual)
    
    # Guardar respuesta
    if respuesta:
        db.guardar_mensaje_whatsapp(numero, respuesta, 'enviado')
    
    # Retornar respuesta para BuilderBot
    return jsonify({
        'response': respuesta,
        'status': 'success'
    })


def procesar_mensaje(numero, mensaje, estado_actual):
    """Procesar mensaje según el estado actual de la conversación"""
    
    # Comandos especiales
    if mensaje in ['cancelar', 'menu', 'hola']:
        db.actualizar_sesion(numero, ESTADOS['NUEVO'])
        return MENU_PRINCIPAL
    
    if mensaje == 'salir':
        db.actualizar_sesion(numero, ESTADOS['NUEVO'])
        return "✅ Sesión finalizada. Escribe *hola* cuando necesites ayuda."
    
    # Procesar según estado
    if estado_actual == ESTADOS['NUEVO']:
        return procesar_menu_principal(numero, mensaje)
    
    elif estado_actual == ESTADOS['BUSCANDO_PACIENTE']:
        return procesar_busqueda_paciente(numero, mensaje)
    
    elif estado_actual == ESTADOS['AGENDANDO_CITA']:
        return procesar_seleccion_paciente_cita(numero, mensaje)
    
    elif estado_actual == ESTADOS['SELECCIONANDO_FECHA']:
        return procesar_seleccion_fecha(numero, mensaje)
    
    elif estado_actual == ESTADOS['SELECCIONANDO_HORA']:
        return procesar_seleccion_hora(numero, mensaje)
    
    elif estado_actual == ESTADOS['VER_CITAS']:
        return procesar_ver_citas(numero, mensaje)
    
    elif estado_actual == ESTADOS['VER_HISTORIAL']:
        return procesar_ver_historial(numero, mensaje)
    
    else:
        return MENU_PRINCIPAL


def procesar_menu_principal(numero, mensaje):
    """Procesar opciones del menú principal"""
    
    if mensaje == '1' or mensaje == 'buscar':
        db.actualizar_sesion(numero, ESTADOS['BUSCANDO_PACIENTE'])
        return "🔍 *Buscar paciente*\n\nEscribe el *nombre completo* o *DNI* del paciente:"
    
    elif mensaje == '2' or mensaje == 'agendar':
        db.actualizar_sesion(numero, ESTADOS['AGENDANDO_CITA'])
        return "📅 *Agendar cita*\n\nEscribe el *nombre completo* o *DNI* del paciente:"
    
    elif mensaje == '3' or mensaje == 'mis citas':
        db.actualizar_sesion(numero, ESTADOS['VER_CITAS'])
        return "📋 *Ver mis citas*\n\nEscribe tu *nombre completo* o *DNI*:"
    
    elif mensaje == '4' or mensaje == 'historial':
        db.actualizar_sesion(numero, ESTADOS['VER_HISTORIAL'])
        return "📋 *Ver historial médico*\n\nEscribe tu *nombre completo* o *DNI*:"
    
    elif mensaje == '5' or mensaje == 'contacto' or mensaje == 'info':
        return """
📍 *INFORMACIÓN DE CONTACTO*

📞 *Teléfono:* (555) 123-4567
🏥 *Dirección:* Av. Principal #123, Centro
⏰ *Horario:* Lunes a Viernes 9:00 - 18:00
📧 *Email:* consultorio@dental.com
💬 *WhatsApp:* Respuesta en 24h

🦷 *Servicios:* Limpiezas, extracciones, endodoncias, ortodoncia, implantes
"""
    
    elif mensaje == '6' or mensaje == 'cancelar cita':
        return procesar_cancelar_cita(numero, mensaje)
    
    else:
        return MENU_PRINCIPAL


def procesar_busqueda_paciente(numero, mensaje):
    """Buscar paciente por nombre o DNI"""
    
    pacientes = db.buscar_paciente(mensaje)
    
    if not pacientes:
        return f"❌ *No se encontraron pacientes* con '{mensaje}'\n\nEscribe *menu* para volver al inicio"
    
    elif len(pacientes) == 1:
        p = pacientes[0]
        respuesta = f"""
✅ *Paciente encontrado:*

*Nombre:* {p['nombre_completo']}
*DNI:* {p['dni'] or 'No registrado'}
*Teléfono:* {p['telefono'] or 'No registrado'}
*Email:* {p['email'] or 'No registrado'}

*Alergias:* {p['alergias'] or 'Ninguna'}
*Condiciones:* {p['condiciones_medicas'] or 'Ninguna'}

📋 *Últimas consultas:*
"""
        historial = db.obtener_historial(p['id'], 3)
        if historial:
            for h in historial:
                fecha = h['fecha_consulta']
                respuesta += f"\n• {fecha}: {h['procedimiento']}"
        else:
            respuesta += "\n• Sin consultas previas"
        
        db.actualizar_sesion(numero, ESTADOS['NUEVO'])
        return respuesta
    
    else:
        # Múltiples resultados
        lista = "\n".join([f"{i+1}. {p['nombre_completo']} (DNI: {p['dni'] or 'N/A'})" 
                          for i, p in enumerate(pacientes)])
        
        # Guardar resultados en sesión
        db.actualizar_sesion(numero, ESTADOS['BUSCANDO_PACIENTE'], 
                            {'resultados': pacientes})
        
        return f"🔍 *Se encontraron {len(pacientes)} pacientes:*\n\n{lista}\n\nResponde con el *número* del paciente para ver detalles completos"


def procesar_seleccion_paciente_cita(numero, mensaje):
    """Seleccionar paciente para agendar cita"""
    
    sesion = db.obtener_o_crear_sesion(numero)
    datos = json.loads(sesion['datos_conversacion']) if sesion['datos_conversacion'] else {}
    
    # Si es un número, seleccionar de resultados previos
    if mensaje.isdigit() and 'resultados' in datos:
        idx = int(mensaje) - 1
        if 0 <= idx < len(datos['resultados']):
            paciente = datos['resultados'][idx]
            
            # Guardar paciente seleccionado
            db.actualizar_sesion(numero, ESTADOS['SELECCIONANDO_FECHA'],
                                {'paciente_id': paciente['id'], 
                                 'paciente_nombre': paciente['nombre_completo']})
            
            # Mostrar fechas disponibles (próximos 7 días)
            fechas = obtener_fechas_disponibles()
            fechas_lista = "\n".join([f"• {fecha}" for fecha in fechas])
            
            return f"""
✅ *Paciente seleccionado:* {paciente['nombre_completo']}

📅 *Fechas disponibles (próximos 7 días):*
{fechas_lista}

Escribe la fecha en formato *DD/MM/AAAA* (ej: 25/12/2024)
"""
    
    # Buscar directamente
    pacientes = db.buscar_paciente(mensaje)
    
    if not pacientes:
        return f"❌ *No se encontraron pacientes* con '{mensaje}'\n\nEscribe *menu* para volver al inicio"
    
    elif len(pacientes) == 1:
        paciente = pacientes[0]
        db.actualizar_sesion(numero, ESTADOS['SELECCIONANDO_FECHA'],
                            {'paciente_id': paciente['id'], 
                             'paciente_nombre': paciente['nombre_completo']})
        
        fechas = obtener_fechas_disponibles()
        fechas_lista = "\n".join([f"• {fecha}" for fecha in fechas])
        
        return f"""
✅ *Paciente seleccionado:* {paciente['nombre_completo']}

📅 *Fechas disponibles (próximos 7 días):*
{fechas_lista}

Escribe la fecha en formato *DD/MM/AAAA* (ej: 25/12/2024)
"""
    
    else:
        lista = "\n".join([f"{i+1}. {p['nombre_completo']} (DNI: {p['dni'] or 'N/A'})" 
                          for i, p in enumerate(pacientes)])
        
        db.actualizar_sesion(numero, ESTADOS['AGENDANDO_CITA'],
                            {'resultados': pacientes})
        
        return f"🔍 *Se encontraron varios pacientes:*\n\n{lista}\n\nResponde con el *número* del paciente"


def procesar_seleccion_fecha(numero, mensaje):
    """Procesar selección de fecha"""
    
    sesion = db.obtener_o_crear_sesion(numero)
    datos = json.loads(sesion['datos_conversacion']) if sesion['datos_conversacion'] else {}
    
    try:
        # Validar formato fecha
        fecha = datetime.strptime(mensaje, '%d/%m/%Y').strftime('%Y-%m-%d')
        fecha_actual = datetime.now().strftime('%Y-%m-%d')
        
        if fecha < fecha_actual:
            return "❌ *Fecha inválida*\n\nLa fecha debe ser futura. Escribe otra fecha o *menu*"
        
        # Verificar horarios disponibles
        horarios = db.obtener_horarios_disponibles(fecha)
        
        if not horarios:
            return "❌ *No hay horarios disponibles* para esta fecha.\n\nElige otra fecha o escribe *menu*"
        
        # Guardar fecha seleccionada
        datos['fecha_cita'] = fecha
        db.actualizar_sesion(numero, ESTADOS['SELECCIONANDO_HORA'], datos)
        
        horarios_lista = "\n".join([f"• {h}" for h in horarios])
        
        return f"""
📅 *Fecha seleccionada:* {mensaje}

⏰ *Horarios disponibles:* 
{horarios_lista}

Escribe la *hora* que prefieras (ej: 10:00, 15:30)
"""
    
    except ValueError:
        return "❌ *Formato incorrecto*\n\nEscribe la fecha en formato *DD/MM/AAAA* (ej: 25/12/2024)"


def procesar_seleccion_hora(numero, mensaje):
    """Procesar selección de hora"""
    
    sesion = db.obtener_o_crear_sesion(numero)
    datos = json.loads(sesion['datos_conversacion']) if sesion['datos_conversacion'] else {}
    
    # Validar formato hora
    if not re.match(r'^([0-1][0-9]|2[0-3]):[0-5][0-9]$', mensaje):
        return "❌ *Formato incorrecto*\n\nEscribe la hora en formato *HH:MM* (ej: 10:00, 15:30)"
    
    hora = mensaje
    fecha = datos.get('fecha_cita')
    paciente_id = datos.get('paciente_id')
    
    # Verificar disponibilidad
    horarios = db.obtener_horarios_disponibles(fecha)
    
    if hora not in horarios:
        return f"❌ *Horario no disponible*\n\nLos horarios disponibles son:\n" + "\n".join([f"• {h}" for h in horarios])
    
    # Guardar hora
    datos['hora_cita'] = hora
    db.actualizar_sesion(numero, ESTADOS['CONFIRMANDO_CITA'], datos)
    
    fecha_mostrar = datetime.strptime(fecha, '%Y-%m-%d').strftime('%d/%m/%Y')
    
    return f"""
📝 *Confirmación de cita*

*Paciente:* {datos['paciente_nombre']}
*Fecha:* {fecha_mostrar}
*Hora:* {hora}

Por favor, escribe el *motivo* de la consulta:
"""


def procesar_ver_citas(numero, mensaje):
    """Ver citas del paciente"""
    
    pacientes = db.buscar_paciente(mensaje)
    
    if not pacientes:
        return f"❌ *No se encontró paciente* con '{mensaje}'\n\nEscribe *menu* para volver al inicio"
    
    paciente = pacientes[0]
    citas = db.obtener_citas_paciente(paciente['id'])
    
    if not citas:
        return f"📅 *Citas para {paciente['nombre_completo']}*\n\nNo tienes citas agendadas"
    
    citas_texto = []
    for cita in citas:
        fecha = datetime.strptime(cita['fecha'], '%Y-%m-%d').strftime('%d/%m/%Y')
        estado_icono = "✅" if cita['estado'] == 'programada' else "❌"
        citas_texto.append(f"{estado_icono} {fecha} - {cita['hora']} - {cita['motivo'] or 'Consulta'}")
    
    db.actualizar_sesion(numero, ESTADOS['NUEVO'])
    
    return f"📅 *Citas para {paciente['nombre_completo']}*\n\n" + "\n".join(citas_texto)


def procesar_ver_historial(numero, mensaje):
    """Ver historial médico"""
    
    pacientes = db.buscar_paciente(mensaje)
    
    if not pacientes:
        return f"❌ *No se encontró paciente* con '{mensaje}'\n\nEscribe *menu* para volver al inicio"
    
    paciente = pacientes[0]
    historial = db.obtener_historial(paciente['id'], 5)
    
    if not historial:
        return f"📋 *Historial de {paciente['nombre_completo']}*\n\nNo hay consultas registradas"
    
    historial_texto = []
    for h in historial:
        fecha = datetime.strptime(h['fecha_consulta'], '%Y-%m-%d').strftime('%d/%m/%Y')
        historial_texto.append(f"📅 *{fecha}*\n• {h['procedimiento']}\n• {h['diagnostico'][:80]}...")
    
    db.actualizar_sesion(numero, ESTADOS['NUEVO'])
    
    return f"📋 *Historial de {paciente['nombre_completo']}*\n\n" + "\n\n".join(historial_texto)


def procesar_cancelar_cita(numero, mensaje):
    """Cancelar una cita existente"""
    # Implementación simplificada
    return """
❌ *Cancelar cita*

Para cancelar una cita, por favor llama al consultorio al 📞 (555) 123-4567
o responde con el ID de la cita que deseas cancelar.

Escribe *menu* para volver al inicio
"""


def obtener_fechas_disponibles():
    """Obtener próximas 7 fechas disponibles"""
    fechas = []
    hoy = datetime.now()
    
    for i in range(1, 8):
        fecha = hoy + timedelta(days=i)
        fechas.append(fecha.strftime('%d/%m/%Y'))
    
    return fechas


# Agregar import necesario
from datetime import timedelta