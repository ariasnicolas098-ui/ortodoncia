from flask import Flask, request, jsonify, render_template, send_from_directory
import sqlite3
import os
from werkzeug.utils import secure_filename
from datetime import datetime, timedelta

# Importar la base de datos y el blueprint de WhatsApp
from database import db
from whatsapp_integration import whatsapp_bp

app = Flask(__name__)

import os

# Configurar carpeta de uploads (volumen persistente en Railway o local)
UPLOAD_FOLDER = os.environ.get('RAILWAY_VOLUME_MOUNT_PATH', '/app/uploads')
if not os.path.exists(UPLOAD_FOLDER):
    UPLOAD_FOLDER = 'uploads'
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB

# Asegurar que exista la carpeta
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
print(f"📁 Carpeta uploads: {app.config['UPLOAD_FOLDER']}")

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
    
    # ========== TABLAS PRINCIPALES ==========
    
    # Tabla pacientes
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS pacientes (
            id SERIAL PRIMARY KEY,
            nombre_completo TEXT NOT NULL,
            dni TEXT UNIQUE,
            fecha_nacimiento DATE,
            telefono TEXT,
            email TEXT,
            direccion TEXT,
            alergias TEXT DEFAULT 'Ninguna',
            medicamentos_actuales TEXT DEFAULT 'Ninguno',
            condiciones_medicas TEXT DEFAULT 'Ninguna',
            fecha_registro TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Tabla historial odontológico
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS historial_odontologico (
            id SERIAL PRIMARY KEY,
            paciente_id INTEGER REFERENCES pacientes(id) ON DELETE CASCADE,
            fecha_consulta DATE,
            hora_consulta TIME,
            motivo_consulta TEXT,
            diagnostico TEXT,
            tratamiento_realizado TEXT,
            dientes_tratados TEXT,
            procedimiento TEXT,
            observaciones TEXT,
            odontologo TEXT
        )
    ''')
    
    # Tabla citas
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS citas (
            id SERIAL PRIMARY KEY,
            paciente_id INTEGER NOT NULL REFERENCES pacientes(id) ON DELETE CASCADE,
            fecha DATE NOT NULL,
            hora TIME NOT NULL,
            motivo TEXT,
            estado TEXT DEFAULT 'programada',
            notas TEXT,
            fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(fecha, hora)
        )
    ''')
    
    # Tabla archivos
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS archivos (
            id SERIAL PRIMARY KEY,
            paciente_id INTEGER REFERENCES pacientes(id) ON DELETE CASCADE,
            nombre TEXT NOT NULL,
            tipo TEXT,
            descripcion TEXT,
            ruta TEXT NOT NULL,
            fecha_subida TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Tablas de WhatsApp
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS whatsapp_mensajes (
            id SERIAL PRIMARY KEY,
            numero TEXT NOT NULL,
            mensaje TEXT,
            tipo TEXT DEFAULT 'recibido',
            fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            procesado INTEGER DEFAULT 0
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS whatsapp_sesiones (
            id SERIAL PRIMARY KEY,
            numero TEXT UNIQUE,
            paciente_id INTEGER REFERENCES pacientes(id),
            estado TEXT DEFAULT 'nuevo',
            ultimo_mensaje TIMESTAMP,
            datos_conversacion TEXT
        )
    ''')
    
    # ========== TABLAS DE ABONOS (NUEVAS) ==========
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS condiciones (
            id SERIAL PRIMARY KEY,
            nombre TEXT NOT NULL UNIQUE,
            precio REAL NOT NULL,
            fecha_registro TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS abonos (
            id SERIAL PRIMARY KEY,
            paciente_id INTEGER NOT NULL REFERENCES pacientes(id) ON DELETE CASCADE,
            condicion_id INTEGER NOT NULL REFERENCES condiciones(id),
            precio_total REAL NOT NULL,
            total_abonado REAL DEFAULT 0,
            estado TEXT DEFAULT 'pendiente',
            notas TEXT,
            fecha_registro TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS pagos (
            id SERIAL PRIMARY KEY,
            abono_id INTEGER NOT NULL REFERENCES abonos(id) ON DELETE CASCADE,
            monto REAL NOT NULL,
            fecha_pago TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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

@app.route('/api/pacientes/<int:paciente_id>', methods=['GET'])
def obtener_paciente(paciente_id):
    """Obtener un paciente específico por ID"""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT * FROM pacientes WHERE id = ?
    """, (paciente_id,))
    
    paciente = cursor.fetchone()
    conn.close()
    
    if paciente:
        return jsonify(dict(paciente))
    else:
        return jsonify({'error': 'Paciente no encontrado'}), 404

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
        WHERE paciente_id = ? 
        ORDER BY fecha DESC, hora DESC
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

# ========== API: CONDICIONES/PRECIOS ==========
@app.route('/api/condiciones', methods=['GET', 'POST'])
def manejar_condiciones():
    conn = get_db()
    cursor = conn.cursor()
    
    if request.method == 'POST':
        data = request.get_json()
        try:
            cursor.execute('''
                INSERT INTO condiciones (nombre, precio) VALUES (?, ?)
            ''', (data['nombre'], data['precio']))
            conn.commit()
            return jsonify({'success': True, 'id': cursor.lastrowid}), 201
        except sqlite3.IntegrityError:
            return jsonify({'error': 'Condición ya existe'}), 400
        finally:
            conn.close()
    
    else:
        cursor.execute('SELECT * FROM condiciones ORDER BY nombre')
        condiciones = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return jsonify(condiciones)

@app.route('/api/condiciones/<int:id>', methods=['PUT', 'DELETE'])
def modificar_condicion(id):
    conn = get_db()
    cursor = conn.cursor()
    
    if request.method == 'PUT':
        data = request.get_json()
        cursor.execute('''
            UPDATE condiciones SET nombre = ?, precio = ? WHERE id = ?
        ''', (data['nombre'], data['precio'], id))
        conn.commit()
        conn.close()
        return jsonify({'success': True})
    
    else:  # DELETE
        cursor.execute('DELETE FROM condiciones WHERE id = ?', (id,))
        conn.commit()
        conn.close()
        return jsonify({'success': True})

# ========== API: ABONOS ==========
@app.route('/api/abonos', methods=['POST'])
def crear_abono():
    data = request.get_json()
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        cursor.execute('''
            INSERT INTO abonos 
            (paciente_id, condicion_id, precio_total, total_abonado, estado, notas)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (
            data['paciente_id'],
            data['condicion_id'],
            data['precio_total'],
            data['abono_inicial'],
            data['estado'],
            data.get('notas', '')
        ))
        
        abono_id = cursor.lastrowid
        
        # Si hay abono inicial, registrarlo como pago
        if data['abono_inicial'] > 0:
            cursor.execute('''
                INSERT INTO pagos (abono_id, monto) VALUES (?, ?)
            ''', (abono_id, data['abono_inicial']))
        
        conn.commit()
        return jsonify({'success': True, 'id': abono_id}), 201
        
    except Exception as e:
        return jsonify({'error': str(e)}), 400
    finally:
        conn.close()

@app.route('/api/abonos/paciente/<int:paciente_id>', methods=['GET'])
def abonos_paciente(paciente_id):
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT a.*, c.nombre as condicion_nombre
        FROM abonos a
        JOIN condiciones c ON a.condicion_id = c.id
        WHERE a.paciente_id = ?
        ORDER BY a.fecha_registro DESC
    ''', (paciente_id,))
    
    abonos = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return jsonify(abonos)

@app.route('/api/abonos/<int:abono_id>/pago', methods=['POST'])
def agregar_pago(abono_id):
    data = request.get_json()
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        # Registrar pago
        cursor.execute('''
            INSERT INTO pagos (abono_id, monto) VALUES (?, ?)
        ''', (abono_id, data['monto']))
        
        # Actualizar total abonado
        cursor.execute('''
            SELECT COALESCE(SUM(monto), 0) as total FROM pagos WHERE abono_id = ?
        ''', (abono_id,))
        total_abonado = cursor.fetchone()['total']
        
        # Obtener precio total
        cursor.execute('SELECT precio_total FROM abonos WHERE id = ?', (abono_id,))
        precio_total = cursor.fetchone()['precio_total']
        
        # Determinar estado
        estado = 'pendiente'
        if total_abonado >= precio_total:
            estado = 'pagado'
        elif total_abonado > 0:
            estado = 'abonado'
        
        cursor.execute('''
            UPDATE abonos SET total_abonado = ?, estado = ? WHERE id = ?
        ''', (total_abonado, estado, abono_id))
        
        conn.commit()
        return jsonify({'success': True, 'estado': estado})
        
    except Exception as e:
        return jsonify({'error': str(e)}), 400
    finally:
        conn.close()

@app.route('/api/abonos/resumen', methods=['GET'])
def resumen_abonos():
    conn = get_db()
    cursor = conn.cursor()
    
    # Pacientes con deuda
    cursor.execute('''
        SELECT COUNT(DISTINCT paciente_id) as total FROM abonos WHERE estado != 'pagado'
    ''')
    pacientes_deuda = cursor.fetchone()['total']
    
    # Ingresos del mes
    hoy = datetime.now()
    primer_dia = hoy.replace(day=1).strftime('%Y-%m-%d')
    cursor.execute('''
        SELECT COALESCE(SUM(monto), 0) as total FROM pagos 
        WHERE date(fecha_pago) >= ?
    ''', (primer_dia,))
    ingresos_mes = cursor.fetchone()['total']
    
    # Por cobrar
    cursor.execute('''
        SELECT COALESCE(SUM(precio_total - total_abonado), 0) as total FROM abonos WHERE estado != 'pagado'
    ''')
    por_cobrar = cursor.fetchone()['total']
    
    # Lista de abonos
    cursor.execute('''
        SELECT a.*, p.nombre_completo as paciente_nombre, c.nombre as condicion_nombre,
               (a.precio_total - a.total_abonado) as saldo
        FROM abonos a
        JOIN pacientes p ON a.paciente_id = p.id
        JOIN condiciones c ON a.condicion_id = c.id
        ORDER BY a.fecha_registro DESC
        LIMIT 50
    ''')
    abonos = [dict(row) for row in cursor.fetchall()]
    
    conn.close()
    
    return jsonify({
        'pacientes_con_deuda': pacientes_deuda,
        'ingresos_mes': ingresos_mes,
        'por_cobrar': por_cobrar,
        'abonos': abonos
    })

# ========== INICIALIZACIÓN ==========
if __name__ == '__main__':
    init_db()
    port = int(os.environ.get('PORT', 5000))
    print(f"🚀 Servidor iniciado en puerto {port}")
    print(f"📁 Panel Admin: /admin")
    print(f"💬 Webhook WhatsApp: /api/whatsapp/webhook")
    app.run(debug=False, host='0.0.0.0', port=port)
else:
    # Para producción (gunicorn)
    init_db()
