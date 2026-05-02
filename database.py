"""
database.py - Gestión unificada de base de datos
Este archivo separa la lógica de BD para que tanto Flask como BuilderBot la usen
"""
import os
import sqlite3

# Intentar importar psycopg2 (solo estará disponible en Railway)
try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
    POSTGRES_AVAILABLE = True
except ImportError:
    POSTGRES_AVAILABLE = False

from datetime import datetime, timedelta
import json


class Database:
    def __init__(self, db_path='consultorio_dental.db'):
        self.db_path = db_path
        
        # OBTENER DATABASE_URL (forzar si no está en variables)
        self.database_url = os.environ.get('DATABASE_URL')
        
        # Si no hay variable de entorno, usar URL directa de Railway
        # (Copia la URL exacta de tu servicio Postgres → Variables → DATABASE_URL)
        if not self.database_url:
            self.database_url = "postgresql://postgres:mmdwFHasTXHqvUovDABIyPqfTWuDULmp@postgres.railway.internal:5432/railway"
        
        self.is_postgres = self.database_url is not None and POSTGRES_AVAILABLE
        
        # DEBUG
        print(f"DEBUG: DATABASE_URL presente = {bool(os.environ.get('DATABASE_URL'))}")
        print(f"DEBUG: POSTGRES_AVAILABLE = {POSTGRES_AVAILABLE}")
        print(f"DEBUG: is_postgres = {self.is_postgres}")
        print(f"DEBUG: URL usada = {self.database_url[:50]}...")
        
        if self.is_postgres:
            print("🐘 Usando PostgreSQL (Railway)")
        else:
            print("🗄️ Usando SQLite (local)")
    
    def get_connection(self):
        if self.is_postgres:
            conn = psycopg2.connect(self.database_url)
            return conn
        else:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON")
            return conn
    
    def get_cursor(self, conn):
        if self.is_postgres:
            return conn.cursor(cursor_factory=RealDictCursor)
        else:
            return conn.cursor()
    
    # ========== PACIENTES ==========
    def buscar_paciente(self, query):
        """Buscar paciente por nombre o DNI"""
        conn = self.get_connection()
        cursor = self.get_cursor(conn)
        
        if self.is_postgres:
            cursor.execute("""
                SELECT id, nombre_completo, dni, telefono, email, direccion,
                       alergias, medicamentos_actuales, condiciones_medicas
                FROM pacientes 
                WHERE LOWER(nombre_completo) LIKE LOWER(%s) OR dni = %s
                LIMIT 5
            """, (f'%{query}%', query))
        else:
            cursor.execute("""
                SELECT id, nombre_completo, dni, telefono, email, direccion,
                       alergias, medicamentos_actuales, condiciones_medicas
                FROM pacientes 
                WHERE LOWER(nombre_completo) LIKE ? OR dni = ?
                LIMIT 5
            """, (f'%{query.lower()}%', query))
        
        pacientes = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return pacientes
    
    def obtener_paciente_por_id(self, paciente_id):
        """Obtener datos completos de un paciente"""
        conn = self.get_connection()
        cursor = self.get_cursor(conn)
        
        if self.is_postgres:
            cursor.execute("SELECT * FROM pacientes WHERE id = %s", (paciente_id,))
        else:
            cursor.execute("SELECT * FROM pacientes WHERE id = ?", (paciente_id,))
        
        paciente = cursor.fetchone()
        conn.close()
        return dict(paciente) if paciente else None
    
    def crear_paciente(self, datos):
        """Crear nuevo paciente"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            if self.is_postgres:
                cursor.execute("""
                    INSERT INTO pacientes 
                    (nombre_completo, dni, telefono, email, direccion, 
                     alergias, medicamentos_actuales, condiciones_medicas)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                """, (
                    datos['nombre_completo'],
                    datos.get('dni', ''),
                    datos.get('telefono', ''),
                    datos.get('email', ''),
                    datos.get('direccion', ''),
                    datos.get('alergias', 'Ninguna'),
                    datos.get('medicamentos', 'Ninguno'),
                    datos.get('condiciones', 'Ninguna')
                ))
                paciente_id = cursor.fetchone()[0]
            else:
                cursor.execute("""
                    INSERT INTO pacientes 
                    (nombre_completo, dni, telefono, email, direccion, 
                     alergias, medicamentos_actuales, condiciones_medicas)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    datos['nombre_completo'],
                    datos.get('dni', ''),
                    datos.get('telefono', ''),
                    datos.get('email', ''),
                    datos.get('direccion', ''),
                    datos.get('alergias', 'Ninguna'),
                    datos.get('medicamentos', 'Ninguno'),
                    datos.get('condiciones', 'Ninguna')
                ))
                paciente_id = cursor.lastrowid
            
            conn.commit()
            conn.close()
            return {'success': True, 'id': paciente_id}
        except Exception as e:
            conn.close()
            return {'success': False, 'error': str(e)}
    
    # ========== CITAS ==========
    def obtener_citas_paciente(self, paciente_id):
        """Obtener citas de un paciente"""
        conn = self.get_connection()
        cursor = self.get_cursor(conn)
        
        if self.is_postgres:
            cursor.execute("""
                SELECT id, fecha, hora, motivo, estado 
                FROM citas 
                WHERE paciente_id = %s 
                ORDER BY fecha DESC, hora DESC
                LIMIT 10
            """, (paciente_id,))
        else:
            cursor.execute("""
                SELECT id, fecha, hora, motivo, estado 
                FROM citas 
                WHERE paciente_id = ? 
                ORDER BY fecha DESC, hora DESC
                LIMIT 10
            """, (paciente_id,))
        
        citas = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return citas
    
    def obtener_horarios_disponibles(self, fecha):
        """Obtener horarios disponibles para una fecha"""
        conn = self.get_connection()
        cursor = self.get_cursor(conn)
        
        # Obtener citas ocupadas
        if self.is_postgres:
            cursor.execute("""
                SELECT hora FROM citas 
                WHERE fecha = %s AND estado = 'programada'
            """, (fecha,))
        else:
            cursor.execute("""
                SELECT hora FROM citas 
                WHERE fecha = ? AND estado = 'programada'
            """, (fecha,))
        
        ocupadas = [row['hora'] for row in cursor.fetchall()]
        conn.close()
        
        # Generar horarios disponibles (9:00 a 18:00 cada 30 min)
        disponibles = []
        hora_actual = 9 * 60
        
        while hora_actual < 18 * 60:
            horas = hora_actual // 60
            minutos = hora_actual % 60
            hora_str = f"{horas:02d}:{minutos:02d}"
            
            if hora_str not in ocupadas:
                disponibles.append(hora_str)
            
            hora_actual += 30
        
        return disponibles
    
    def crear_cita(self, paciente_id, fecha, hora, motivo):
        """Crear nueva cita"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # Verificar disponibilidad
        if self.is_postgres:
            cursor.execute("""
                SELECT id FROM citas 
                WHERE fecha = %s AND hora = %s AND estado = 'programada'
            """, (fecha, hora))
        else:
            cursor.execute("""
                SELECT id FROM citas 
                WHERE fecha = ? AND hora = ? AND estado = 'programada'
            """, (fecha, hora))
        
        if cursor.fetchone():
            conn.close()
            return {'success': False, 'error': 'Horario no disponible'}
        
        try:
            if self.is_postgres:
                cursor.execute("""
                    INSERT INTO citas (paciente_id, fecha, hora, motivo, estado)
                    VALUES (%s, %s, %s, %s, 'programada')
                    RETURNING id
                """, (paciente_id, fecha, hora, motivo))
                cita_id = cursor.fetchone()[0]
            else:
                cursor.execute("""
                    INSERT INTO citas (paciente_id, fecha, hora, motivo, estado)
                    VALUES (?, ?, ?, ?, 'programada')
                """, (paciente_id, fecha, hora, motivo))
                cita_id = cursor.lastrowid
            
            conn.commit()
            conn.close()
            return {'success': True, 'id': cita_id}
        except Exception as e:
            conn.close()
            return {'success': False, 'error': str(e)}
    
    def cancelar_cita(self, cita_id):
        """Cancelar una cita"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        if self.is_postgres:
            cursor.execute("""
                UPDATE citas SET estado = 'cancelada' WHERE id = %s
            """, (cita_id,))
        else:
            cursor.execute("""
                UPDATE citas SET estado = 'cancelada' WHERE id = ?
            """, (cita_id,))
        
        conn.commit()
        conn.close()
        return {'success': True}
    
    # ========== HISTORIAL ==========
    def obtener_historial(self, paciente_id, limite=5):
        """Obtener historial de consultas"""
        conn = self.get_connection()
        cursor = self.get_cursor(conn)
        
        if self.is_postgres:
            cursor.execute("""
                SELECT fecha_consulta, procedimiento, diagnostico, 
                       tratamiento_realizado, odontologo
                FROM historial_odontologico 
                WHERE paciente_id = %s 
                ORDER BY fecha_consulta DESC
                LIMIT %s
            """, (paciente_id, limite))
        else:
            cursor.execute("""
                SELECT fecha_consulta, procedimiento, diagnostico, 
                       tratamiento_realizado, odontologo
                FROM historial_odontologico 
                WHERE paciente_id = ? 
                ORDER BY fecha_consulta DESC
                LIMIT ?
            """, (paciente_id, limite))
        
        historial = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return historial
    
    def crear_consulta(self, datos):
        """Registrar nueva consulta"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            if self.is_postgres:
                cursor.execute("""
                    INSERT INTO historial_odontologico 
                    (paciente_id, fecha_consulta, hora_consulta, motivo_consulta,
                     diagnostico, tratamiento_realizado, procedimiento, odontologo)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    datos['paciente_id'],
                    datos.get('fecha', datetime.now().strftime('%Y-%m-%d')),
                    datos.get('hora', datetime.now().strftime('%H:%M')),
                    datos.get('motivo', ''),
                    datos.get('diagnostico', ''),
                    datos.get('tratamiento', ''),
                    datos.get('procedimiento', 'Consulta'),
                    datos.get('odontologo', 'Dr. General')
                ))
            else:
                cursor.execute("""
                    INSERT INTO historial_odontologico 
                    (paciente_id, fecha_consulta, hora_consulta, motivo_consulta,
                     diagnostico, tratamiento_realizado, procedimiento, odontologo)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    datos['paciente_id'],
                    datos.get('fecha', datetime.now().strftime('%Y-%m-%d')),
                    datos.get('hora', datetime.now().strftime('%H:%M')),
                    datos.get('motivo', ''),
                    datos.get('diagnostico', ''),
                    datos.get('tratamiento', ''),
                    datos.get('procedimiento', 'Consulta'),
                    datos.get('odontologo', 'Dr. General')
                ))
            
            conn.commit()
            conn.close()
            return {'success': True}
        except Exception as e:
            conn.close()
            return {'success': False, 'error': str(e)}
    
    # ========== WHATSAPP ==========
    def guardar_mensaje_whatsapp(self, numero, mensaje, tipo='recibido'):
        """Guardar mensaje de WhatsApp en BD"""
        conn = self.get_connection()
        cursor = conn.cursor()
        fecha = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        if self.is_postgres:
            cursor.execute("""
                INSERT INTO whatsapp_mensajes (numero, mensaje, tipo, fecha)
                VALUES (%s, %s, %s, %s)
            """, (numero, mensaje, tipo, fecha))
        else:
            cursor.execute("""
                INSERT INTO whatsapp_mensajes (numero, mensaje, tipo, fecha)
                VALUES (?, ?, ?, ?)
            """, (numero, mensaje, tipo, fecha))
        
        conn.commit()
        conn.close()
    
    def obtener_mensajes_pendientes(self, limite=10):
        """Obtener mensajes no procesados"""
        conn = self.get_connection()
        cursor = self.get_cursor(conn)
        
        if self.is_postgres:
            cursor.execute("""
                SELECT * FROM whatsapp_mensajes 
                WHERE procesado = 0 
                ORDER BY fecha ASC 
                LIMIT %s
            """, (limite,))
        else:
            cursor.execute("""
                SELECT * FROM whatsapp_mensajes 
                WHERE procesado = 0 
                ORDER BY fecha ASC 
                LIMIT ?
            """, (limite,))
        
        mensajes = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return mensajes
    
    def marcar_mensaje_procesado(self, mensaje_id):
        """Marcar mensaje como procesado"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        if self.is_postgres:
            cursor.execute("""
                UPDATE whatsapp_mensajes SET procesado = 1 WHERE id = %s
            """, (mensaje_id,))
        else:
            cursor.execute("""
                UPDATE whatsapp_mensajes SET procesado = 1 WHERE id = ?
            """, (mensaje_id,))
        
        conn.commit()
        conn.close()
    
    def obtener_o_crear_sesion(self, numero):
        """Obtener o crear sesión de chat"""
        conn = self.get_connection()
        cursor = self.get_cursor(conn)
        
        if self.is_postgres:
            cursor.execute("""
                SELECT * FROM whatsapp_sesiones WHERE numero = %s
            """, (numero,))
        else:
            cursor.execute("""
                SELECT * FROM whatsapp_sesiones WHERE numero = ?
            """, (numero,))
        
        sesion = cursor.fetchone()
        
        if not sesion:
            # Crear nueva sesión
            fecha = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            if self.is_postgres:
                cursor.execute("""
                    INSERT INTO whatsapp_sesiones (numero, estado, ultimo_mensaje)
                    VALUES (%s, 'nuevo', %s)
                    RETURNING id
                """, (numero, fecha))
                sesion_id = cursor.fetchone()[0]
                cursor.execute("SELECT * FROM whatsapp_sesiones WHERE id = %s", (sesion_id,))
            else:
                cursor.execute("""
                    INSERT INTO whatsapp_sesiones (numero, estado, ultimo_mensaje)
                    VALUES (?, 'nuevo', ?)
                """, (numero, fecha))
                sesion_id = cursor.lastrowid
                cursor.execute("SELECT * FROM whatsapp_sesiones WHERE id = ?", (sesion_id,))
            
            sesion = cursor.fetchone()
            conn.commit()
        
        conn.close()
        return dict(sesion) if sesion else None
    
    def actualizar_sesion(self, numero, estado, datos=None):
        """Actualizar estado de sesión"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        datos_json = json.dumps(datos) if datos else None
        fecha = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        if self.is_postgres:
            cursor.execute("""
                UPDATE whatsapp_sesiones 
                SET estado = %s, datos_conversacion = %s, ultimo_mensaje = %s
                WHERE numero = %s
            """, (estado, datos_json, fecha, numero))
        else:
            cursor.execute("""
                UPDATE whatsapp_sesiones 
                SET estado = ?, datos_conversacion = ?, ultimo_mensaje = ?
                WHERE numero = ?
            """, (estado, datos_json, fecha, numero))
        
        conn.commit()
        conn.close()
    
    # ========== ESTADÍSTICAS ==========
    def obtener_estadisticas_whatsapp(self):
        """Obtener estadísticas de WhatsApp"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        stats = {}
        
        # Total mensajes
        cursor.execute("SELECT COUNT(*) FROM whatsapp_mensajes")
        stats['total_mensajes'] = cursor.fetchone()[0]
        
        # Mensajes hoy
        if self.is_postgres:
            cursor.execute("""
                SELECT COUNT(*) FROM whatsapp_mensajes 
                WHERE date(fecha) = CURRENT_DATE
            """)
            cursor.execute("""
                SELECT COUNT(*) FROM whatsapp_sesiones 
                WHERE estado != 'finalizado' 
                AND ultimo_mensaje >= NOW() - INTERVAL '1 day'
            """)
        else:
            cursor.execute("""
                SELECT COUNT(*) FROM whatsapp_mensajes 
                WHERE date(fecha) = date('now')
            """)
            cursor.execute("""
                SELECT COUNT(*) FROM whatsapp_sesiones 
                WHERE estado != 'finalizado' AND julianday('now') - julianday(ultimo_mensaje) < 1
            """)
        
        stats['mensajes_hoy'] = cursor.fetchone()[0]
        stats['sesiones_activas'] = cursor.fetchone()[0]
        
        conn.close()
        return stats


# Instancia global para usar en toda la app
db = Database()
