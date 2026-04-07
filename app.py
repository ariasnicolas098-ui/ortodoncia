from flask import Flask, request, jsonify, render_template, send_from_directory
import sqlite3
import os
from werkzeug.utils import secure_filename
from datetime import datetime, timedelta

# Importar la base de datos y el blueprint de WhatsApp
from database import db
from whatsapp_integration import whatsapp_bp

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

# Registrar blueprint de WhatsApp
app.register_blueprint(whatsapp_bp)

# Crear carpetas necesarias
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs('templates', exist_ok=True)

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'pdf', 'doc', 'docx'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def get_db():
    """Mantener compatibilidad con código existente"""
    return db.get_connection()

# ========== INICIALIZAR DB ==========
def init_db():
    """Inicializar todas las tablas necesarias"""
    conn = db.get_connection()
    cursor = conn.cursor()
    
    # Tabla pacientes
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS pacientes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre_completo TEXT NOT NULL,
            dni TEXT UNIQUE,
            fecha_nacimiento DATE,
            telefono TEXT,
            email TEXT,
            direccion TEXT,
            alergias TEXT DEFAULT 'Ninguna',
            medicamentos_actuales TEXT DEFAULT 'Ninguno',
            condiciones_medicas TEXT DEFAULT 'Ninguna',
            fecha_registro DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Tabla historial odontológico
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS historial_odontologico (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            paciente_id INTEGER,
            fecha_consulta DATE,
            hora_consulta TIME,
            motivo_consulta TEXT,
            diagnostico TEXT,
            tratamiento_realizado TEXT,
            dientes_tratados TEXT,
            procedimiento TEXT,
            observaciones TEXT,
            odontologo TEXT,
            FOREIGN KEY (paciente_id) REFERENCES pacientes(id)
        )
    ''')
    
    # Tabla citas
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS citas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            paciente_id INTEGER NOT NULL,
            fecha DATE NOT NULL,
            hora TIME NOT NULL,
            motivo TEXT,
            estado TEXT DEFAULT 'programada',
            notas TEXT,
            fecha_creacion DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (paciente_id) REFERENCES pacientes(id),
            UNIQUE(fecha, hora)
        )
    ''')
    
    # Tabla archivos
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS archivos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            paciente_id INTEGER,
            nombre TEXT NOT NULL,
            tipo TEXT,
            descripcion TEXT,
            ruta TEXT NOT NULL,
            fecha_subida DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (paciente_id) REFERENCES pacientes(id)
        )
    ''')
    
    # Tablas de WhatsApp
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS whatsapp_mensajes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            numero TEXT NOT NULL,
            mensaje TEXT,
            tipo TEXT DEFAULT 'recibido',
            fecha DATETIME DEFAULT CURRENT_TIMESTAMP,
            procesado INTEGER DEFAULT 0
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS whatsapp_sesiones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            numero TEXT UNIQUE,
            paciente_id INTEGER,
            estado TEXT DEFAULT 'nuevo',
            ultimo_mensaje DATETIME,
            datos_conversacion TEXT,
            FOREIGN KEY (paciente_id) REFERENCES pacientes(id)
        )
    ''')
    conn.commit()
    conn.close()
    print("✅ Base de datos inicializada correctamente")   

# ========== RUTAS DE VISTAS ==========
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/admin')
def admin():
    return render_template('admin.html')

@app.route('/uploads/<path:filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

# ========== API: BÚSQUEDA ==========
@app.route('/api/buscar')
def buscar_paciente():
    query = request.args.get('q', '').strip().lower()
    
    if not query:
        return jsonify([])
    
    conn = get_db()
    cursor = conn.cursor()
    
    # Búsqueda exacta o parcial
    cursor.execute("""
        SELECT * FROM pacientes 
        WHERE LOWER(nombre_completo) LIKE ? 
        ORDER BY nombre_completo
    """, (f'%{query}%',))
    
    pacientes = cursor.fetchall()
    resultado = []
    
    for paciente in pacientes:
        p = dict(paciente)
        
        # Obtener historial
        cursor.execute("""
            SELECT * FROM historial_odontologico 
            WHERE paciente_id = ? 
            ORDER BY fecha_consulta DESC
        """, (p['id'],))
        p['historial'] = [dict(h) for h in cursor.fetchall()]
        
        # Obtener archivos
        cursor.execute("""
            SELECT * FROM archivos 
            WHERE paciente_id = ? 
            ORDER BY fecha_subida DESC
        """, (p['id'],))
        p['archivos'] = [dict(a) for a in cursor.fetchall()]
        
        resultado.append(p)
    
    # Búsqueda difusa si no hay resultados exactos
    if not resultado:
        from thefuzz import fuzz
        cursor.execute("SELECT * FROM pacientes")
        todos = cursor.fetchall()
        
        for p in todos:
            if fuzz.partial_ratio(query, p['nombre_completo'].lower()) > 60:
                pa = dict(p)
                cursor.execute("""
                    SELECT * FROM historial_odontologico 
                    WHERE paciente_id = ? 
                    ORDER BY fecha_consulta DESC
                """, (p['id'],))
                pa['historial'] = [dict(h) for h in cursor.fetchall()]
                
                cursor.execute("""
                    SELECT * FROM archivos 
                    WHERE paciente_id = ? 
                    ORDER BY fecha_subida DESC
                """, (p['id'],))
                pa['archivos'] = [dict(a) for a in cursor.fetchall()]
                
                resultado.append(pa)
    
    conn.close()
    return jsonify(resultado)

# ========== API: PACIENTES ==========
@app.route('/api/pacientes', methods=['GET', 'POST'])
def manejar_pacientes():
    conn = get_db()
    cursor = conn.cursor()
    
    if request.method == 'POST':
        data = request.get_json()
        
        try:
            cursor.execute("""
                INSERT INTO pacientes 
                (nombre_completo, dni, fecha_nacimiento, telefono, email, 
                 direccion, alergias, medicamentos_actuales, condiciones_medicas)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                data['nombre_completo'],
                data.get('dni'),
                data.get('fecha_nacimiento'),
                data.get('telefono'),
                data.get('email'),
                data.get('direccion'),
                data.get('alergias', 'Ninguna'),
                data.get('medicamentos_actuales', 'Ninguno'),
                data.get('condiciones_medicas', 'Ninguna')
            ))
            conn.commit()
            return jsonify({'success': True, 'id': cursor.lastrowid}), 201
            
        except sqlite3.IntegrityError:
            return jsonify({'error': 'DNI ya registrado'}), 400
        finally:
            conn.close()
    
    else:  # GET
        filtro = request.args.get('filtro', '')
        
        if filtro:
            cursor.execute("""
                SELECT id, nombre_completo as nombre, telefono,
                       (SELECT MAX(fecha_consulta) FROM historial_odontologico 
                        WHERE paciente_id = pacientes.id) as ultima_visita,
                       (SELECT MIN(fecha) FROM citas 
                        WHERE paciente_id = pacientes.id AND fecha >= date('now') AND estado = 'programada') as proxima_cita
                FROM pacientes 
                WHERE LOWER(nombre_completo) LIKE ?
                ORDER BY nombre_completo
            """, (f'%{filtro.lower()}%',))
        else:
            cursor.execute("""
                SELECT id, nombre_completo as nombre, telefono,
                       (SELECT MAX(fecha_consulta) FROM historial_odontologico 
                        WHERE paciente_id = pacientes.id) as ultima_visita,
                       (SELECT MIN(fecha) FROM citas 
                        WHERE paciente_id = pacientes.id AND fecha >= date('now') AND estado = 'programada') as proxima_cita
                FROM pacientes 
                ORDER BY nombre_completo
                LIMIT 50
            """)
        
        pacientes = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return jsonify(pacientes)

# ========== API: CONSULTAS ==========
@app.route('/api/consultas', methods=['POST'])
def crear_consulta():
    data = request.get_json()
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            INSERT INTO historial_odontologico 
            (paciente_id, fecha_consulta, hora_consulta, motivo_consulta, diagnostico, 
             tratamiento_realizado, dientes_tratados, procedimiento, 
             observaciones, odontologo)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            data['paciente_id'],
            data['fecha_consulta'],
            data.get('hora_consulta'),
            data['motivo_consulta'],
            data['diagnostico'],
            data['tratamiento_realizado'],
            data.get('dientes_tratados'),
            data['procedimiento'],
            data.get('observaciones'),
            data.get('odontologo')
        ))
        conn.commit()
        return jsonify({'success': True}), 201
        
    except Exception as e:
        return jsonify({'error': str(e)}), 400
    finally:
        conn.close()

# ========== API: CITAS (NUEVO) ==========
@app.route('/api/citas/disponibles', methods=['GET'])
def horarios_disponibles():
    fecha = request.args.get('fecha')
    if not fecha:
        return jsonify({'error': 'Fecha requerida'}), 400
    
    conn = get_db()
    cursor = conn.cursor()
    
    # Horario de trabajo: 9:00 a 18:00, cada 30 minutos
    horarios = []
    hora_actual = 9 * 60  # 9:00 en minutos
    hora_fin = 18 * 60     # 18:00 en minutos
    
    # Obtener citas ocupadas para esa fecha
    cursor.execute("""
        SELECT hora FROM citas 
        WHERE fecha = ? AND estado = 'programada'
    """, (fecha,))
    citas_ocupadas = [row['hora'] for row in cursor.fetchall()]
    
    while hora_actual < hora_fin:
        horas = hora_actual // 60
        minutos = hora_actual % 60
        hora_str = f"{horas:02d}:{minutos:02d}"
        
        # Verificar si está ocupada (comparar solo HH:MM)
        ocupada = any(str(cita)[:5] == hora_str for cita in citas_ocupadas)
        
        horarios.append({
            'hora': hora_str,
            'disponible': not ocupada
        })
        
        hora_actual += 30  # Intervalos de 30 minutos
    
    conn.close()
    return jsonify(horarios)

@app.route('/api/citas', methods=['POST'])
def crear_cita():
    data = request.get_json()
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        # Verificar disponibilidad
        cursor.execute("""
            SELECT id FROM citas 
            WHERE fecha = ? AND hora = ? AND estado = 'programada'
        """, (data['fecha'], data['hora']))
        
        if cursor.fetchone():
            return jsonify({'error': 'Horario ya ocupado'}), 409
        
        cursor.execute("""
            INSERT INTO citas (paciente_id, fecha, hora, motivo, estado)
            VALUES (?, ?, ?, ?, 'programada')
        """, (
            data['paciente_id'],
            data['fecha'],
            data['hora'],
            data.get('motivo')
        ))
        
        conn.commit()
        return jsonify({'success': True, 'id': cursor.lastrowid}), 201
        
    except Exception as e:
        return jsonify({'error': str(e)}), 400
    finally:
        conn.close()

@app.route('/api/citas/paciente/<int:paciente_id>', methods=['GET'])
def citas_paciente(paciente_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM citas 
        WHERE paciente_id = ? AND fecha >= date('now')
        ORDER BY fecha, hora
    """, (paciente_id,))
    citas = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return jsonify(citas)

# ========== API: ARCHIVOS ==========
@app.route('/api/archivos', methods=['POST'])
def subir_archivo():
    if 'archivo' not in request.files:
        return jsonify({'error': 'No se envió archivo'}), 400
    
    file = request.files['archivo']
    if file.filename == '':
        return jsonify({'error': 'Nombre de archivo vacío'}), 400
    
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        unique_filename = f"{timestamp}_{filename}"
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
        file.save(filepath)
        
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO archivos (paciente_id, nombre, tipo, descripcion, ruta)
            VALUES (?, ?, ?, ?, ?)
        """, (
            request.form['paciente_id'], 
            filename, 
            request.form['tipo'], 
            request.form.get('descripcion'), 
            unique_filename
        ))
        conn.commit()
        conn.close()
        
        return jsonify({'success': True}), 201
    
    return jsonify({'error': 'Tipo de archivo no permitido'}), 400

@app.route('/api/archivos/<int:paciente_id>', methods=['GET'])
def listar_archivos(paciente_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM archivos 
        WHERE paciente_id = ? 
        ORDER BY fecha_subida DESC
    """, (paciente_id,))
    archivos = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return jsonify(archivos)

@app.route('/api/archivos/<int:archivo_id>', methods=['DELETE'])
def eliminar_archivo(archivo_id):
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("SELECT ruta FROM archivos WHERE id = ?", (archivo_id,))
    archivo = cursor.fetchone()
    
    if archivo:
        try:
            os.remove(os.path.join(app.config['UPLOAD_FOLDER'], archivo['ruta']))
        except:
            pass
        
        cursor.execute("DELETE FROM archivos WHERE id = ?", (archivo_id,))
        conn.commit()
    
    conn.close()
    return jsonify({'success': True})

# ========== API: ESTADÍSTICAS ==========
@app.route('/api/estadisticas')
def get_estadisticas():
    conn = get_db()
    cursor = conn.cursor()
    
    # Total pacientes
    cursor.execute("SELECT COUNT(*) as total FROM pacientes")
    total_pacientes = cursor.fetchone()['total']
    
    # Consultas este mes
    hoy = datetime.now()
    primer_dia_mes = hoy.replace(day=1).strftime('%Y-%m-%d')
    cursor.execute("""
        SELECT COUNT(*) as total FROM historial_odontologico 
        WHERE fecha_consulta >= ?
    """, (primer_dia_mes,))
    consultas_mes = cursor.fetchone()['total']
    
    # Próximas citas (próximos 30 días)
    fecha_limite = (hoy + timedelta(days=30)).strftime('%Y-%m-%d')
    cursor.execute("""
        SELECT COUNT(*) as total FROM citas 
        WHERE fecha BETWEEN date('now') AND ? AND estado = 'programada'
    """, (fecha_limite,))
    proximas_citas = cursor.fetchone()['total']
    
    conn.close()
    
    return jsonify({
        'total_pacientes': total_pacientes,
        'consultas_mes': consultas_mes,
        'proximas_citas': proximas_citas
    })

# ========== DEBUG ==========
@app.route('/api/debug/archivos')
def debug_archivos():
    import os
    ruta = app.config['UPLOAD_FOLDER']
    archivos = os.listdir(ruta) if os.path.exists(ruta) else []
    return jsonify({
        'ruta_absoluta': os.path.abspath(ruta),
        'archivos_encontrados': archivos,
        'total': len(archivos)
    })

# ========== NUEVOS ENDPOINTS PARA WHATSAPP EN ADMIN ==========
@app.route('/api/whatsapp/status', methods=['GET'])
def whatsapp_status():
    """Estado del sistema de WhatsApp"""
    stats = db.obtener_estadisticas_whatsapp()
    return jsonify({
        'status': 'active',
        'stats': stats,
        'webhook_url': '/api/whatsapp/webhook'
    })

@app.route('/api/whatsapp/mensajes', methods=['GET'])
def whatsapp_mensajes():
    """Obtener mensajes recientes"""
    conn = db.get_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT * FROM whatsapp_mensajes 
        ORDER BY fecha DESC 
        LIMIT 50
    """)
    
    mensajes = [dict(row) for row in cursor.fetchall()]
    conn.close()
    
    return jsonify(mensajes)

@app.route('/api/whatsapp/citas/manana', methods=['GET'])
def whatsapp_citas_manana():
    """Obtener citas para mañana"""
    manana = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')
    
    conn = db.get_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT c.*, p.nombre_completo, p.telefono
        FROM citas c
        JOIN pacientes p ON c.paciente_id = p.id
        WHERE c.fecha = ? AND c.estado = 'programada'
    """, (manana,))
    
    citas = [dict(row) for row in cursor.fetchall()]
    conn.close()
    
    return jsonify(citas)

@app.route('/api/whatsapp/recordatorio/<int:cita_id>', methods=['POST'])
def whatsapp_enviar_recordatorio(cita_id):
    """Enviar recordatorio de cita por WhatsApp"""
    # Esta función llamará al webhook de BuilderBot
    # Por ahora solo marcamos que se envió
    return jsonify({'success': True})

# ========== INICIALIZACIÓN ==========
if __name__ == '__main__':
    init_db()
    print("🚀 Servidor iniciado en http://localhost:5000")
    print("📁 Panel Admin: http://localhost:5000/admin")
    print("💬 Webhook WhatsApp: http://localhost:5000/api/whatsapp/webhook")
    app.run(debug=True, host='0.0.0.0', port=5000)
else:
    # Para producción (gunicorn)
    init_db()
