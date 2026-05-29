from flask import Flask, request, jsonify, render_template, send_from_directory
import os
from werkzeug.utils import secure_filename
from datetime import datetime, timedelta

from database import db

try:
    from whatsapp_integration import whatsapp_bp
    WHATSAPP_BP_EXISTS = True
except ImportError:
    WHATSAPP_BP_EXISTS = False

app = Flask(__name__)

UPLOAD_FOLDER = os.environ.get('RAILWAY_VOLUME_MOUNT_PATH', '/app/uploads')
if not os.path.exists(UPLOAD_FOLDER):
    UPLOAD_FOLDER = 'uploads'
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

if WHATSAPP_BP_EXISTS:
    app.register_blueprint(whatsapp_bp)

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'pdf', 'doc', 'docx'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def get_db():
    return db.get_connection()

def execute_query(cursor, query, params=None, returning=False):
    if db.is_postgres:
        query = query.replace('?', '%s')
        if returning and 'INSERT INTO' in query and 'RETURNING' not in query.upper():
            query = query.rstrip(';') + ' RETURNING id;'
    
    if params:
        cursor.execute(query, params)
    else:
        cursor.execute(query)
    
    return cursor

def init_db():
    conn = db.get_connection()
    cursor = db.get_cursor(conn)
    
    if db.is_postgres:
        pk_type = "SERIAL PRIMARY KEY"
    else:
        pk_type = "INTEGER PRIMARY KEY AUTOINCREMENT"
    
    print("🔧 Creando tablas si no existen...")
    
    cursor.execute(f'''
        CREATE TABLE IF NOT EXISTS pacientes (
            id {pk_type},
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
    
    cursor.execute(f'''
        CREATE TABLE IF NOT EXISTS historial_odontologico (
            id {pk_type},
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
    
    cursor.execute(f'''
        CREATE TABLE IF NOT EXISTS citas (
            id {pk_type},
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
    
    cursor.execute(f'''
        CREATE TABLE IF NOT EXISTS archivos (
            id {pk_type},
            paciente_id INTEGER REFERENCES pacientes(id) ON DELETE CASCADE,
            nombre TEXT NOT NULL,
            tipo TEXT,
            descripcion TEXT,
            ruta TEXT NOT NULL,
            fecha_subida TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    cursor.execute(f'''
        CREATE TABLE IF NOT EXISTS whatsapp_mensajes (
            id {pk_type},
            numero TEXT NOT NULL,
            mensaje TEXT,
            tipo TEXT DEFAULT 'recibido',
            fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            procesado INTEGER DEFAULT 0
        )
    ''')
    
    cursor.execute(f'''
        CREATE TABLE IF NOT EXISTS whatsapp_sesiones (
            id {pk_type},
            numero TEXT UNIQUE,
            paciente_id INTEGER REFERENCES pacientes(id),
            estado TEXT DEFAULT 'nuevo',
            ultimo_mensaje TIMESTAMP,
            datos_conversacion TEXT
        )
    ''')
    
    cursor.execute(f'''
        CREATE TABLE IF NOT EXISTS condiciones (
            id {pk_type},
            nombre TEXT NOT NULL UNIQUE,
            precio REAL NOT NULL,
            fecha_registro TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    cursor.execute(f'''
        CREATE TABLE IF NOT EXISTS abonos (
            id {pk_type},
            paciente_id INTEGER NOT NULL REFERENCES pacientes(id) ON DELETE CASCADE,
            condicion_id INTEGER NOT NULL REFERENCES condiciones(id),
            precio_total REAL NOT NULL,
            total_abonado REAL DEFAULT 0,
            estado TEXT DEFAULT 'pendiente',
            notas TEXT,
            fecha_registro TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    cursor.execute(f'''
        CREATE TABLE IF NOT EXISTS pagos (
            id {pk_type},
            abono_id INTEGER NOT NULL REFERENCES abonos(id) ON DELETE CASCADE,
            monto REAL NOT NULL,
            fecha_pago TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    conn.commit()
    conn.close()
    print("✅ Base de datos inicializada correctamente")

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/admin')
def admin():
    return render_template('admin.html')

@app.route('/uploads/<path:filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/api/buscar')
def buscar_paciente():
    query = request.args.get('q', '').strip().lower()
    
    if not query:
        return jsonify([])
    
    conn = get_db()
    cursor = db.get_cursor(conn)
    
    execute_query(cursor, """
        SELECT * FROM pacientes 
        WHERE LOWER(nombre_completo) LIKE ?
        ORDER BY nombre_completo
    """, (f'%{query}%',))
    
    pacientes = cursor.fetchall()
    resultado = []
    
    for paciente in pacientes:
        p = dict(paciente)
        
        execute_query(cursor, """
            SELECT * FROM historial_odontologico 
            WHERE paciente_id = ? 
            ORDER BY fecha_consulta DESC
        """, (p['id'],))
        p['historial'] = [dict(h) for h in cursor.fetchall()]
        
        execute_query(cursor, """
            SELECT * FROM archivos 
            WHERE paciente_id = ? 
            ORDER BY fecha_subida DESC
        """, (p['id'],))
        p['archivos'] = [dict(a) for a in cursor.fetchall()]
        
        resultado.append(p)
    
    if not resultado:
        try:
            from thefuzz import fuzz
            execute_query(cursor, "SELECT * FROM pacientes")
            todos = cursor.fetchall()
            
            for p in todos:
                if fuzz.partial_ratio(query, p['nombre_completo'].lower()) > 60:
                    pa = dict(p)
                    execute_query(cursor, """
                        SELECT * FROM historial_odontologico 
                        WHERE paciente_id = ? 
                        ORDER BY fecha_consulta DESC
                    """, (p['id'],))
                    pa['historial'] = [dict(h) for h in cursor.fetchall()]
                    
                    execute_query(cursor, """
                        SELECT * FROM archivos 
                        WHERE paciente_id = ? 
                        ORDER BY fecha_subida DESC
                    """, (p['id'],))
                    pa['archivos'] = [dict(a) for a in cursor.fetchall()]
                    
                    resultado.append(pa)
        except ImportError:
            pass
    
    conn.close()
    return jsonify(resultado)

@app.route('/api/pacientes', methods=['GET', 'POST'])
def manejar_pacientes():
    conn = get_db()
    cursor = db.get_cursor(conn)
    
    if request.method == 'POST':
        data = request.get_json()
        
        try:
            if db.is_postgres:
                execute_query(cursor, """
                    INSERT INTO pacientes 
                    (nombre_completo, dni, fecha_nacimiento, telefono, email, 
                     direccion, alergias, medicamentos_actuales, condiciones_medicas)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    RETURNING id
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
                ), returning=True)
                result = cursor.fetchone()
                last_id = result['id'] if isinstance(result, dict) else result[0]
            else:
                execute_query(cursor, """
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
                last_id = cursor.lastrowid
            
            conn.commit()
            conn.close()
            return jsonify({'success': True, 'id': last_id}), 201
            
        except Exception as e:
            conn.close()
            return jsonify({'error': str(e)}), 400
    
    filtro = request.args.get('filtro', '')
    
    if filtro:
        execute_query(cursor, """
            SELECT id, nombre_completo as nombre, telefono,
                   (SELECT MAX(fecha_consulta) FROM historial_odontologico 
                    WHERE paciente_id = pacientes.id) as ultima_visita,
                   (SELECT MIN(fecha) FROM citas 
                    WHERE paciente_id = pacientes.id AND fecha >= CURRENT_DATE AND estado = 'programada') as proxima_cita
            FROM pacientes 
            WHERE LOWER(nombre_completo) LIKE ?
            ORDER BY nombre_completo
        """, (f'%{filtro.lower()}%',))
    else:
        execute_query(cursor, """
            SELECT id, nombre_completo as nombre, telefono,
                   (SELECT MAX(fecha_consulta) FROM historial_odontologico 
                    WHERE paciente_id = pacientes.id) as ultima_visita,
                   (SELECT MIN(fecha) FROM citas 
                    WHERE paciente_id = pacientes.id AND fecha >= CURRENT_DATE AND estado = 'programada') as proxima_cita
            FROM pacientes 
            ORDER BY nombre_completo
            LIMIT 50
        """)
    
    pacientes = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return jsonify(pacientes)

@app.route('/api/pacientes/<int:paciente_id>', methods=['GET'])
def obtener_paciente(paciente_id):
    conn = get_db()
    cursor = db.get_cursor(conn)
    
    # Función auxiliar para convertir fechas/horas a texto
    def clean_row(row):
        r = dict(row)
        for key, value in r.items():
            # Si el valor tiene método isoformat (fechas/horas), lo convertimos a string
            if hasattr(value, 'isoformat'):
                r[key] = value.isoformat()
        return r

    try:
        # 1. Datos básicos
        query = "SELECT * FROM pacientes WHERE id = %s" if db.is_postgres else "SELECT * FROM pacientes WHERE id = ?"
        cursor.execute(query, (paciente_id,))
        paciente = cursor.fetchone()
        
        if not paciente:
            conn.close()
            return jsonify({'error': 'Paciente no encontrado'}), 404
        
        p = clean_row(paciente)
        
        # 2. Historial
        query = "SELECT * FROM historial_odontologico WHERE paciente_id = %s" if db.is_postgres else "SELECT * FROM historial_odontologico WHERE paciente_id = ?"
        cursor.execute(query, (paciente_id,))
        p['historial'] = [clean_row(row) for row in cursor.fetchall()]
        
        # 3. Archivos
        query = "SELECT * FROM archivos WHERE paciente_id = %s" if db.is_postgres else "SELECT * FROM archivos WHERE paciente_id = ?"
        cursor.execute(query, (paciente_id,))
        archivos = []
        for row in cursor.fetchall():
            a = clean_row(row)
            a['url'] = f"/uploads/{a['ruta']}"
            archivos.append(a)
        p['archivos'] = archivos
        
        # 4. Citas
        query = "SELECT * FROM citas WHERE paciente_id = %s" if db.is_postgres else "SELECT * FROM citas WHERE paciente_id = ?"
        cursor.execute(query, (paciente_id,))
        p['citas'] = [clean_row(row) for row in cursor.fetchall()]
        
        # 5. Abonos
        query = """
            SELECT a.*, c.nombre as condicion_nombre
            FROM abonos a JOIN condiciones c ON a.condicion_id = c.id
            WHERE a.paciente_id = %s
        """ if db.is_postgres else """
            SELECT a.*, c.nombre as condicion_nombre
            FROM abonos a JOIN condiciones c ON a.condicion_id = c.id
            WHERE a.paciente_id = ?
        """
        cursor.execute(query, (paciente_id,))
        p['abonos'] = [clean_row(row) for row in cursor.fetchall()]
        
        conn.close()
        return jsonify(p)

    except Exception as e:
        conn.close()
        print(f"❌ ERROR en obtener_paciente: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/consultas', methods=['POST'])
def crear_consulta():
    data = request.get_json()
    conn = get_db()
    cursor = db.get_cursor(conn)
    
    try:
        execute_query(cursor, """
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
        conn.close()
        return jsonify({'success': True}), 201
        
    except Exception as e:
        conn.close()
        return jsonify({'error': str(e)}), 400

@app.route('/api/citas/disponibles', methods=['GET'])
def horarios_disponibles():
    fecha = request.args.get('fecha')
    if not fecha:
        return jsonify({'error': 'Fecha requerida'}), 400
    
    conn = get_db()
    cursor = db.get_cursor(conn)
    
    horarios = []
    hora_actual = 9 * 60
    hora_fin = 18 * 60
    
    execute_query(cursor, """
        SELECT hora FROM citas 
        WHERE fecha = ? AND estado = 'programada'
    """, (fecha,))
    
    citas_ocupadas = [str(row['hora'])[:5] if isinstance(row, dict) else str(row[0])[:5] for row in cursor.fetchall()]
    
    while hora_actual < hora_fin:
        horas = hora_actual // 60
        minutos = hora_actual % 60
        hora_str = f"{horas:02d}:{minutos:02d}"
        
        ocupada = hora_str in citas_ocupadas
        
        horarios.append({
            'hora': hora_str,
            'disponible': not ocupada
        })
        
        hora_actual += 30
    
    conn.close()
    return jsonify(horarios)

@app.route('/api/citas', methods=['POST'])
def crear_cita():
    data = request.get_json()
    conn = get_db()
    cursor = db.get_cursor(conn)
    
    try:
        execute_query(cursor, """
            SELECT id FROM citas 
            WHERE fecha = ? AND hora = ? AND estado = 'programada'
        """, (data['fecha'], data['hora']))
        
        if cursor.fetchone():
            conn.close()
            return jsonify({'error': 'Horario ya ocupado'}), 409
        
        execute_query(cursor, """
            INSERT INTO citas (paciente_id, fecha, hora, motivo, estado)
            VALUES (?, ?, ?, ?, 'programada')
            RETURNING id
        """, (
            data['paciente_id'],
            data['fecha'],
            data['hora'],
            data.get('motivo')
        ), returning=True)
        
        conn.commit()
        
        result = cursor.fetchone()
        cita_id = result['id'] if isinstance(result, dict) else result[0]
        
        conn.close()
        return jsonify({'success': True, 'id': cita_id}), 201
        
    except Exception as e:
        conn.close()
        return jsonify({'error': str(e)}), 400

@app.route('/api/citas/paciente/<int:paciente_id>', methods=['GET'])
def citas_paciente(paciente_id):
    conn = get_db()
    cursor = db.get_cursor(conn)
    
    execute_query(cursor, """
        SELECT * FROM citas 
        WHERE paciente_id = ? 
        ORDER BY fecha DESC, hora DESC
    """, (paciente_id,))
    
    citas = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return jsonify(citas)

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
        cursor = db.get_cursor(conn)
        
        execute_query(cursor, """
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
    cursor = db.get_cursor(conn)
    
    execute_query(cursor, """
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
    cursor = db.get_cursor(conn)
    
    execute_query(cursor, "SELECT ruta FROM archivos WHERE id = ?", (archivo_id,))
    archivo = cursor.fetchone()
    
    if archivo:
        try:
            ruta = archivo['ruta'] if isinstance(archivo, dict) else archivo[0]
            os.remove(os.path.join(app.config['UPLOAD_FOLDER'], ruta))
        except:
            pass
        
        execute_query(cursor, "DELETE FROM archivos WHERE id = ?", (archivo_id,))
        conn.commit()
    
    conn.close()
    return jsonify({'success': True})

@app.route('/api/estadisticas')
def get_estadisticas():
    conn = get_db()
    cursor = db.get_cursor(conn)
    
    execute_query(cursor, "SELECT COUNT(*) as total FROM pacientes")
    total_pacientes = cursor.fetchone()
    total_pacientes = total_pacientes['total'] if isinstance(total_pacientes, dict) else total_pacientes[0]
    
    hoy = datetime.now()
    primer_dia_mes = hoy.replace(day=1).strftime('%Y-%m-%d')
    
    execute_query(cursor, """
        SELECT COUNT(*) as total FROM historial_odontologico 
        WHERE fecha_consulta >= ?
    """, (primer_dia_mes,))
    
    consultas_mes = cursor.fetchone()
    consultas_mes = consultas_mes['total'] if isinstance(consultas_mes, dict) else consultas_mes[0]
    
    fecha_limite = (hoy + timedelta(days=30)).strftime('%Y-%m-%d')
    
    execute_query(cursor, """
        SELECT COUNT(*) as total FROM citas 
        WHERE fecha BETWEEN CURRENT_DATE AND ? AND estado = 'programada'
    """, (fecha_limite,))
    
    proximas_citas = cursor.fetchone()
    proximas_citas = proximas_citas['total'] if isinstance(proximas_citas, dict) else proximas_citas[0]
    
    conn.close()
    
    return jsonify({
        'total_pacientes': total_pacientes,
        'consultas_mes': consultas_mes,
        'proximas_citas': proximas_citas
    })

@app.route('/api/debug/archivos')
def debug_archivos():
    ruta = app.config['UPLOAD_FOLDER']
    archivos = os.listdir(ruta) if os.path.exists(ruta) else []
    return jsonify({
        'ruta_absoluta': os.path.abspath(ruta),
        'archivos_encontrados': archivos,
        'total': len(archivos)
    })

@app.route('/api/whatsapp/status', methods=['GET'])
def whatsapp_status():
    stats = db.obtener_estadisticas_whatsapp()
    return jsonify({
        'status': 'active',
        'stats': stats,
        'webhook_url': '/api/whatsapp/webhook'
    })

@app.route('/api/whatsapp/mensajes', methods=['GET'])
def whatsapp_mensajes():
    conn = get_db()
    cursor = db.get_cursor(conn)
    
    execute_query(cursor, """
        SELECT * FROM whatsapp_mensajes 
        ORDER BY fecha DESC 
        LIMIT 50
    """)
    
    mensajes = [dict(row) for row in cursor.fetchall()]
    conn.close()
    
    return jsonify(mensajes)

@app.route('/api/whatsapp/citas/manana', methods=['GET'])
def whatsapp_citas_manana():
    manana = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')
    
    conn = get_db()
    cursor = db.get_cursor(conn)
    
    execute_query(cursor, """
        SELECT c.*, p.nombre_completo, p.telefono
        FROM citas c
        JOIN pacientes p ON c.paciente_id = p.id
        WHERE c.fecha = ? AND c.estado = 'programada'
    """, (manana,))
    
    citas = [dict(row) for row in cursor.fetchall()]
    conn.close()
    
    return jsonify(citas)

@app.route('/api/condiciones', methods=['GET', 'POST'])
def manejar_condiciones():
    conn = get_db()
    cursor = db.get_cursor(conn)
    
    if request.method == 'POST':
        data = request.get_json()
        try:
            execute_query(cursor, '''
                INSERT INTO condiciones (nombre, precio) VALUES (?, ?)
            ''', (data['nombre'], data['precio']))
            conn.commit()
            conn.close()
            return jsonify({'success': True}), 201
        except Exception as e:
            conn.close()
            return jsonify({'error': str(e)}), 400
    
    else:
        execute_query(cursor, 'SELECT * FROM condiciones ORDER BY nombre')
        condiciones = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return jsonify(condiciones)

@app.route('/api/condiciones/<int:id>', methods=['PUT', 'DELETE'])
def modificar_condicion(id):
    conn = get_db()
    cursor = db.get_cursor(conn)
    
    if request.method == 'PUT':
        data = request.get_json()
        execute_query(cursor, '''
            UPDATE condiciones SET nombre = ?, precio = ? WHERE id = ?
        ''', (data['nombre'], data['precio'], id))
        conn.commit()
        conn.close()
        return jsonify({'success': True})
    
    else:
        execute_query(cursor, 'DELETE FROM condiciones WHERE id = ?', (id,))
        conn.commit()
        conn.close()
        return jsonify({'success': True})

@app.route('/api/abonos', methods=['POST'])
def crear_abono():
    data = request.get_json()
    
    if not data:
        return jsonify({'error': 'No se recibieron datos'}), 400
    
    required_fields = ['paciente_id', 'condicion_id', 'precio_total']
    for field in required_fields:
        if field not in data:
            return jsonify({'error': f'Falta el campo {field}'}), 400

    conn = get_db()
    cursor = db.get_cursor(conn)
    
    try:
        execute_query(cursor, "SELECT precio FROM condiciones WHERE id = ?", (data['condicion_id'],))
        condicion = cursor.fetchone()
        
        if not condicion:
            conn.close()
            return jsonify({'error': 'La condición seleccionada no existe'}), 400

        abono_inicial = float(data.get('abono_inicial', 0))
        precio_total = float(data['precio_total'])
        
        estado = 'pendiente'
        if abono_inicial >= precio_total:
            estado = 'pagado'
        elif abono_inicial > 0:
            estado = 'abonado'

        execute_query(cursor, '''
            INSERT INTO abonos 
            (paciente_id, condicion_id, precio_total, total_abonado, estado, notas)
            VALUES (?, ?, ?, ?, ?, ?)
            RETURNING id
        ''', (
            data['paciente_id'],
            data['condicion_id'],
            precio_total,
            abono_inicial,
            estado,
            data.get('notas', '')
        ), returning=True)
        
        # CORRECCIÓN: Usar ['id'] en lugar de [0]
        result = cursor.fetchone()
        abono_id = result['id'] if isinstance(result, dict) else result[0]
        
        if abono_inicial > 0:
            execute_query(cursor, '''
                INSERT INTO pagos (abono_id, monto) VALUES (?, ?)
            ''', (abono_id, abono_inicial))
        
        conn.commit()
        conn.close()
        return jsonify({'success': True, 'id': abono_id, 'estado': estado}), 201
        
    except Exception as e:
        conn.rollback()
        conn.close()
        print(f"❌ Error en crear_abono: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 400

@app.route('/api/abonos/paciente/<int:paciente_id>', methods=['GET'])
def abonos_paciente(paciente_id):
    conn = get_db()
    cursor = db.get_cursor(conn)
    
    execute_query(cursor, '''
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
    cursor = db.get_cursor(conn)
    
    try:
        # 1. Insertar el nuevo pago
        execute_query(cursor, '''
            INSERT INTO pagos (abono_id, monto) VALUES (?, ?)
        ''', (abono_id, data['monto']))
        
        # 2. Calcular el total abonado hasta ahora
        execute_query(cursor, '''
            SELECT COALESCE(SUM(monto), 0) as total FROM pagos WHERE abono_id = ?
        ''', (abono_id,))
        
        total_abonado = cursor.fetchone()
        # CORRECCIÓN IMPORTANTE para PostgreSQL
        total_abonado = total_abonado['total'] if isinstance(total_abonado, dict) else total_abonado[0]
        
        # 3. Obtener el precio total para comparar
        execute_query(cursor, 'SELECT precio_total FROM abonos WHERE id = ?', (abono_id,))
        precio_total = cursor.fetchone()
        # CORRECCIÓN IMPORTANTE para PostgreSQL
        precio_total = precio_total['precio_total'] if isinstance(precio_total, dict) else precio_total[0]
        
        # 4. Determinar el nuevo estado
        estado = 'pendiente'
        if total_abonado >= precio_total:
            estado = 'pagado'
        elif total_abonado > 0:
            estado = 'abonado'
        
        # 5. Actualizar el abono
        execute_query(cursor, '''
            UPDATE abonos SET total_abonado = ?, estado = ? WHERE id = ?
        ''', (total_abonado, estado, abono_id))
        
        conn.commit()
        conn.close()
        return jsonify({'success': True, 'estado': estado})
        
    except Exception as e:
        conn.close()
        return jsonify({'error': str(e)}), 400

@app.route('/api/abonos/resumen', methods=['GET'])
def resumen_abonos():
    conn = get_db()
    cursor = db.get_cursor(conn)
    
    try:
        execute_query(cursor, '''
            SELECT COUNT(DISTINCT paciente_id) as total FROM abonos WHERE estado != 'pagado'
        ''')
        row = cursor.fetchone()
        pacientes_deuda = int(row['total'] if isinstance(row, dict) else row[0] or 0)
        
        hoy = datetime.now()
        primer_dia = hoy.replace(day=1).strftime('%Y-%m-%d')
        
        if db.is_postgres:
            execute_query(cursor, '''
                SELECT COALESCE(SUM(monto), 0) as total FROM pagos 
                WHERE fecha_pago >= ?
            ''', (primer_dia,))
        else:
            execute_query(cursor, '''
                SELECT COALESCE(SUM(monto), 0) as total FROM pagos 
                WHERE date(fecha_pago) >= ?
            ''', (primer_dia,))
        
        row = cursor.fetchone()
        ingresos_mes = float(row['total'] if isinstance(row, dict) else row[0] or 0)
        
        execute_query(cursor, '''
            SELECT COALESCE(SUM(precio_total - total_abonado), 0) as total 
            FROM abonos WHERE estado != 'pagado'
        ''')
        row = cursor.fetchone()
        por_cobrar = float(row['total'] if isinstance(row, dict) else row[0] or 0)
        
        execute_query(cursor, '''
            SELECT a.*, p.nombre_completo as paciente_nombre, c.nombre as condicion_nombre,
                   (a.precio_total - a.total_abonado) as saldo
            FROM abonos a
            JOIN pacientes p ON a.paciente_id = p.id
            JOIN condiciones c ON a.condicion_id = c.id
            ORDER BY a.fecha_registro DESC
            LIMIT 50
        ''')
        
        abonos = [dict(row) for row in cursor.fetchall()]
        
        for a in abonos:
            a['saldo'] = float(a['saldo'] or 0)
            a['precio_total'] = float(a['precio_total'] or 0)
            a['total_abonado'] = float(a['total_abonado'] or 0)
        
        conn.close()
        
        return jsonify({
            'pacientes_con_deuda': pacientes_deuda,
            'ingresos_mes': ingresos_mes,
            'por_cobrar': por_cobrar,
            'abonos': abonos
        })
        
    except Exception as e:
        conn.close()
        print(f"❌ Error en resumen_abonos: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    init_db()
    port = int(os.environ.get('PORT', 5000))
    print(f"🚀 Servidor iniciado en puerto {port}")
    print(f"📁 Panel Admin: /admin")
    app.run(debug=False, host='0.0.0.0', port=port)
else:
    init_db()
