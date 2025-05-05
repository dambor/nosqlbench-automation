from flask import Flask, request, jsonify, send_file, send_from_directory
from flask_cors import CORS
import os
import re
import yaml
import json
import tempfile
import zipfile
import io
import subprocess
import logging
import time
import threading
import shutil

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__, static_folder='static')
CORS(app)  # Enable CORS for all routes

# Directory to store generated YAML files
YAML_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'yaml_files')
os.makedirs(YAML_DIR, exist_ok=True)

# Path to NoSQLBench JAR file
NB_JAR_PATH = os.environ.get('NB_JAR_PATH', './nb5.jar')

# Create static directory if it doesn't exist
STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static')
os.makedirs(STATIC_DIR, exist_ok=True)

# Dictionary to store running processes and their outputs
running_processes = {}

# Database connection pool
db_connections = {}

@app.route('/')
def index():
    """Serve the main HTML interface"""
    return send_from_directory('static', 'index.html')

@app.route('/api/parse-cql', methods=['POST'])
def parse_cql():
    """Parse CQL schema and return table structures"""
    data = request.json
    cql_schema = data.get('schema', '')
    
    try:
        tables = parse_cql_schema(cql_schema)
        return jsonify({'success': True, 'tables': tables})
    except Exception as e:
        logger.error(f"Error parsing CQL: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 400

@app.route('/api/generate-yaml', methods=['POST'])
def generate_yaml():
    """Generate NoSQLBench YAML files from CQL schema"""
    data = request.json
    keyspace_name = data.get('keyspace', '')
    cql_schema = data.get('schema', '')
    num_cycles = data.get('cycles', 10000000)
    threads = data.get('threads', 'auto')
    
    try:
        # Parse CQL schema to extract table information
        tables = parse_cql_schema(cql_schema)
        
        if not tables:
            return jsonify({'success': False, 'error': 'No valid CREATE TABLE statements found'}), 400
        
        # Generate YAML files for each table
        yaml_files = generate_yaml_files(keyspace_name, tables, num_cycles, threads)
        
        # Create response with file IDs and content
        response_data = []
        for file_id, file_info in yaml_files.items():
            response_data.append({
                'id': file_id,
                'name': file_info['name'],
                'content': file_info['content']
            })
        
        return jsonify({'success': True, 'yaml_files': response_data})
    except Exception as e:
        logger.error(f"Error generating YAML: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 400

@app.route('/api/download-yaml', methods=['GET'])
def download_yaml():
    """Download a specific YAML file by ID"""
    file_id = request.args.get('id', '')
    
    if not file_id or not os.path.exists(os.path.join(YAML_DIR, f"{file_id}.yaml")):
        return jsonify({'success': False, 'error': 'File not found'}), 404
    
    return send_file(os.path.join(YAML_DIR, f"{file_id}.yaml"), as_attachment=True)

@app.route('/api/download-all', methods=['GET'])
def download_all_yaml():
    """Download all generated YAML files as a ZIP archive"""
    # Create a ZIP file in memory
    memory_file = io.BytesIO()
    with zipfile.ZipFile(memory_file, 'w') as zf:
        for filename in os.listdir(YAML_DIR):
            if filename.endswith('.yaml'):
                file_path = os.path.join(YAML_DIR, filename)
                zf.write(file_path, arcname=filename)
    
    memory_file.seek(0)
    return send_file(memory_file, download_name='nosqlbench-yamls.zip', as_attachment=True)

@app.route('/api/connect', methods=['POST'])
def connect_database():
    """Connect to Cassandra/DSE/Astra database"""
    data = request.json
    db_type = data.get('type', 'cassandra')
    
    connection_id = f"conn_{int(time.time())}"
    
    try:
        if db_type == 'cassandra' or db_type == 'dse':
            hosts = data.get('hosts', '127.0.0.1').split(',')
            port = int(data.get('port', 9042))
            username = data.get('username', '')
            password = data.get('password', '')
            datacenter = data.get('datacenter', 'datacenter1')
            
            # Store connection info without testing - we'll test when actually connecting
            db_connections[connection_id] = {
                'type': db_type,
                'hosts': hosts,
                'port': port,
                'datacenter': datacenter,
                'username': username,
                'password': password
            }
            
            logger.info(f"Created connection ID: {connection_id} for {db_type} at {hosts}")
            
            return jsonify({
                'success': True, 
                'connection_id': connection_id,
                'info': {
                    'hosts': hosts,
                    'datacenter': datacenter,
                    'type': db_type.upper()
                }
            })
            
        elif db_type == 'astra':
            astra_db_id = data.get('astra_db_id')
            astra_token = data.get('astra_token')
            astra_region = data.get('astra_region')
            
            # Store connection info
            db_connections[connection_id] = {
                'type': 'astra',
                'astra_db_id': astra_db_id,
                'astra_token': astra_token,
                'astra_region': astra_region
            }
            
            logger.info(f"Created connection ID: {connection_id} for Astra DB: {astra_db_id}")
            
            return jsonify({
                'success': True, 
                'connection_id': connection_id,
                'info': {
                    'database': astra_db_id,
                    'region': astra_region,
                    'type': 'Astra DB'
                }
            })
        
        # If we get here, the database type is not supported
        return jsonify({'success': False, 'error': f"Unsupported database type: {db_type}"}), 400
            
    except Exception as e:
        logger.error(f"Error connecting to database: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/list-connections', methods=['GET'])
def list_connections():
    """List all active database connections"""
    connections = []
    for conn_id, conn_info in db_connections.items():
        connections.append({
            'id': conn_id,
            'type': conn_info.get('type', 'unknown'),
            'hosts': conn_info.get('hosts', []),
            'datacenter': conn_info.get('datacenter', '')
        })
    
    return jsonify({'success': True, 'connections': connections})

@app.route('/api/run-nosqlbench-direct', methods=['POST'])
def run_nosqlbench_direct():
    """Run NoSQLBench command directly with direct output"""
    data = request.json
    yaml_id = data.get('yaml_id', '')
    keyspace = data.get('keyspace', '')
    
    # Find the YAML file
    yaml_path = None
    for filename in os.listdir(YAML_DIR):
        if filename.endswith('.yaml'):
            if yaml_id in filename:
                yaml_path = os.path.join(YAML_DIR, filename)
                break
    
    if not yaml_path:
        return jsonify({'success': False, 'error': 'YAML file not found'}), 404
    
    try:
        # Build a simple, reliable command
        cmd = [
            'java',
            '-jar',
            os.path.abspath(NB_JAR_PATH),
            yaml_path,
            f'host=127.0.0.1',
            f'localdc=datacenter1',
            f'keyspace={keyspace}',
            '--progress',
            'console:1s'
        ]
        
        # Log what we're about to do
        logger.info(f"Executing: {' '.join(cmd)}")
        
        # Run process with direct execution and wait for result
        try:
            # Use timeout to prevent hanging
            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=60  # 60 seconds timeout
            )
            
            # Check result
            if result.returncode == 0:
                return jsonify({
                    'success': True,
                    'output': result.stdout,
                    'command': ' '.join(cmd)
                })
            else:
                logger.error(f"Command failed with return code {result.returncode}")
                logger.error(f"Error output: {result.stderr}")
                return jsonify({
                    'success': False,
                    'error': result.stderr,
                    'output': result.stdout,
                    'command': ' '.join(cmd)
                })
                
        except subprocess.TimeoutExpired:
            # Process is taking too long - probably still running in background
            return jsonify({
                'success': True,
                'output': "Command started but is taking longer than 60 seconds. NoSQLBench is likely still running in the background.",
                'command': ' '.join(cmd),
                'timeout': True
            })
            
    except Exception as e:
        logger.error(f"Error running NoSQLBench: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/diagnose', methods=['GET'])
def diagnose():
    """Diagnostic endpoint to check system configuration"""
    diagnostic_info = {
        "success": True,
        "system": os.name,
        "current_directory": os.getcwd(),
        "yaml_directory": os.path.abspath(YAML_DIR),
        "yaml_files_exist": os.path.exists(YAML_DIR),
        "yaml_files_count": len([f for f in os.listdir(YAML_DIR) if f.endswith('.yaml')]) if os.path.exists(YAML_DIR) else 0,
        "yaml_files": [f for f in os.listdir(YAML_DIR) if f.endswith('.yaml')] if os.path.exists(YAML_DIR) else [],
        "nb_jar_path": os.path.abspath(NB_JAR_PATH),
        "nb_jar_exists": os.path.exists(NB_JAR_PATH),
        "java_version": None,
        "java_path": None
    }
    
    # Check Java
    try:
        java_output = subprocess.check_output(["java", "-version"], stderr=subprocess.STDOUT, text=True)
        diagnostic_info["java_version"] = java_output.strip()
        
        java_path = subprocess.check_output(["which", "java"], text=True).strip()
        diagnostic_info["java_path"] = java_path
    except Exception as e:
        diagnostic_info["java_error"] = str(e)
    
    # Try a simple test command
    if diagnostic_info["nb_jar_exists"]:
        try:
            test_output = subprocess.check_output(
                ["java", "-jar", os.path.abspath(NB_JAR_PATH), "--version"], 
                stderr=subprocess.STDOUT, 
                text=True
            )
            diagnostic_info["nb_test"] = True
            diagnostic_info["nb_version"] = test_output.strip()
        except subprocess.CalledProcessError as e:
            diagnostic_info["nb_test"] = False
            diagnostic_info["nb_test_error"] = e.output.strip()
            diagnostic_info["nb_test_returncode"] = e.returncode
        except Exception as e:
            diagnostic_info["nb_test"] = False
            diagnostic_info["nb_test_error"] = str(e)
    
    return jsonify(diagnostic_info)

@app.route('/api/run-test', methods=['POST'])
def run_test():
    """Run a test NoSQLBench command with complete error output"""
    data = request.json
    yaml_name = data.get('yaml_name', '')
    keyspace = data.get('keyspace', 'centralpayment')
    
    try:
        # Try to find the YAML file
        yaml_files = [f for f in os.listdir(YAML_DIR) if f.endswith('.yaml')]
        yaml_path = None
        
        if yaml_name:
            # Look for exact match first
            if yaml_name in yaml_files:
                yaml_path = os.path.join(YAML_DIR, yaml_name)
            else:
                # Look for partial match
                for filename in yaml_files:
                    if yaml_name in filename:
                        yaml_path = os.path.join(YAML_DIR, filename)
                        break
        elif yaml_files:
            # Just use the first YAML file
            yaml_path = os.path.join(YAML_DIR, yaml_files[0])
        
        if not yaml_path:
            return jsonify({
                'success': False, 
                'error': 'No YAML files found',
                'yaml_dir': os.path.abspath(YAML_DIR),
                'yaml_files': yaml_files
            }), 404
        
        # Build simple test command
        cmd = [
            'java',
            '-jar',
            os.path.abspath(NB_JAR_PATH),
            yaml_path,
            f'host=127.0.0.1',
            f'localdc=datacenter1',
            f'keyspace={keyspace}'
        ]
        
        logger.info(f"Running test command: {' '.join(cmd)}")
        
        try:
            # Run with complete output capture
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            stdout, stderr = process.communicate(timeout=5)
            
            return jsonify({
                'success': process.returncode == 0,
                'returncode': process.returncode,
                'command': ' '.join(cmd),
                'stdout': stdout,
                'stderr': stderr,
                'yaml_path': yaml_path,
                'nb_jar_path': os.path.abspath(NB_JAR_PATH),
                'cwd': os.getcwd()
            })
            
        except subprocess.TimeoutExpired:
            process.kill()
            stdout, stderr = process.communicate()
            
            return jsonify({
                'success': True,
                'timeout': True,
                'command': ' '.join(cmd),
                'stdout': stdout,
                'stderr': stderr,
                'message': 'Command started but still running after timeout'
            })
            
    except Exception as e:
        logger.error(f"Error running test: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e),
            'traceback': traceback.format_exc()
        }), 500
    
@app.route('/api/run-nosqlbench', methods=['POST'])
def run_nosqlbench():
    """Run NoSQLBench command against the database"""
    data = request.json
    yaml_id = data.get('yaml_id', '')
    connection_id = data.get('connection_id', '')
    keyspace = data.get('keyspace', '')
    additional_options = data.get('options', '')
    
    # Debug logging
    logger.info(f"Run request: yaml_id={yaml_id}, connection_id={connection_id}, keyspace={keyspace}")
    
    # Validate YAML file exists
    yaml_path = None
    for filename in os.listdir(YAML_DIR):
        if filename.endswith('.yaml'):
            # Look for exact match or match by ID prefix
            if filename == f"{yaml_id}.yaml" or filename.startswith(f"{yaml_id}_"):
                yaml_path = os.path.join(YAML_DIR, filename)
                logger.info(f"Found YAML file: {yaml_path}")
                break
    
    # If not found by ID, try by name
    if not yaml_path:
        name_parts = yaml_id.split('_')
        if len(name_parts) > 0:
            base_name = name_parts[0]
            for filename in os.listdir(YAML_DIR):
                if filename.endswith('.yaml') and base_name in filename:
                    yaml_path = os.path.join(YAML_DIR, filename)
                    logger.info(f"Found YAML file by name: {yaml_path}")
                    break
    
    # Last resort - use latest YAML file
    if not yaml_path:
        yaml_files = [f for f in os.listdir(YAML_DIR) if f.endswith('.yaml')]
        if yaml_files:
            yaml_files.sort(key=lambda f: os.path.getmtime(os.path.join(YAML_DIR, f)), reverse=True)
            yaml_path = os.path.join(YAML_DIR, yaml_files[0])
            logger.info(f"Using most recent YAML file: {yaml_path}")
        else:
            return jsonify({'success': False, 'error': 'No YAML files found'}), 404
    
    # Ensure NoSQLBench JAR exists
    if not os.path.exists(NB_JAR_PATH):
        return jsonify({'success': False, 'error': f'NoSQLBench JAR not found at {NB_JAR_PATH}'}), 400
    
    # Get connection info
    connection = None
    if connection_id in db_connections:
        connection = db_connections[connection_id]
    else:
        connection = {
            'type': 'cassandra',
            'hosts': ['127.0.0.1'],
            'datacenter': 'datacenter1',
            'username': '',
            'password': ''
        }
        logger.warning(f"Connection ID {connection_id} not found. Using default connection.")
    
    try:
        # Build NoSQLBench command
        cmd = []
        
        # Use absolute path to java
        java_path = 'java'
        cmd.append(java_path)
        
        # Add options for Java
        cmd.extend(['-jar'])
        
        # Add absolute path to NoSQLBench JAR
        cmd.append(os.path.abspath(NB_JAR_PATH))
        
        # Add YAML file path
        cmd.append(os.path.abspath(yaml_path))
        
        # Add connection details as separate arguments
        hosts = ','.join(connection.get('hosts', ['127.0.0.1']))
        cmd.append(f"host={hosts}")
        cmd.append(f"localdc={connection.get('datacenter', 'datacenter1')}")
        cmd.append(f"keyspace={keyspace}")
        
        # Add credentials if provided
        if connection.get('username') and connection.get('password'):
            cmd.append(f"username={connection['username']}")
            cmd.append(f"password={connection['password']}")
        
        # Add progress reporting as separate arguments
        cmd.append("--progress")
        cmd.append("console:1s")
        
        # Add any additional options as separate arguments
        if additional_options:
            cmd.extend(additional_options.split())
        
        # Log the command
        cmd_str = ' '.join(cmd)
        logger.info(f"Executing NoSQLBench command: {cmd_str}")
        
              
        # Create a unique process ID
        process_id = f"proc_{int(time.time())}"
        
        # Function to run the process
        def run_process(cmd, process_id):
            start_time = time.time()
            try:
                # Start the process
                process = subprocess.Popen(
                    cmd, 
                    stdout=subprocess.PIPE, 
                    stderr=subprocess.PIPE,
                    text=True,
                    bufsize=1,  # Line buffered
                    universal_newlines=True
                )
                
                # Store process info
                running_processes[process_id] = {
                    'process': process,
                    'command': cmd_str,
                    'start_time': start_time,
                    'status': 'running',
                    'output': '',
                    'error': ''
                }
                
                # Capture output in real-time
                stdout_thread = threading.Thread(target=read_output, args=(process.stdout, process_id, 'output'))
                stderr_thread = threading.Thread(target=read_output, args=(process.stderr, process_id, 'error'))
                stdout_thread.daemon = True
                stderr_thread.daemon = True
                stdout_thread.start()
                stderr_thread.start()
                
                # Wait for process to complete
                return_code = process.wait()
                end_time = time.time()
                
                # Update process info
                running_processes[process_id]['status'] = 'completed' if return_code == 0 else 'failed'
                running_processes[process_id]['return_code'] = return_code
                running_processes[process_id]['end_time'] = end_time
                running_processes[process_id]['duration'] = end_time - start_time
                
                if return_code != 0:
                    logger.error(f"Process {process_id} failed with code {return_code}")
                else:
                    logger.info(f"Process {process_id} completed successfully in {end_time - start_time:.2f} seconds")
            except Exception as e:
                logger.error(f"Error running process {process_id}: {str(e)}")
                if process_id in running_processes:
                    running_processes[process_id]['status'] = 'failed'
                    running_processes[process_id]['error'] += f"\nError: {str(e)}"
                    running_processes[process_id]['end_time'] = time.time()
                    running_processes[process_id]['duration'] = time.time() - start_time
        
        # Function to read output in real-time
        def read_output(pipe, process_id, output_type):
            for line in pipe:
                if process_id in running_processes:
                    running_processes[process_id][output_type] += line
        
        # Start the process in a separate thread
        thread = threading.Thread(target=run_process, args=(cmd, process_id))
        thread.daemon = True
        thread.start()
        
        # Return initial process info
        return jsonify({
            'success': True,
            'process_id': process_id,
            'command': cmd_str,
            'message': 'NoSQLBench process started'
        })
        
    except Exception as e:
        logger.error(f"Error setting up NoSQLBench process: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/process/<process_id>', methods=['GET'])
def get_process_status(process_id):
    """Get status and output of a running process"""
    if process_id not in running_processes:
        return jsonify({'success': False, 'error': 'Process not found'}), 404
    
    process_info = running_processes[process_id]
    
    # Create response with process information
    response = {
        'success': True,
        'process_id': process_id,
        'status': process_info['status'],
        'command': process_info['command'],
        'start_time': process_info['start_time'],
        'elapsed_time': time.time() - process_info['start_time']
    }
    
    # Add output and error if available
    if 'output' in process_info:
        response['output'] = process_info['output']
    
    if 'error' in process_info:
        response['error'] = process_info['error']
    
    if 'return_code' in process_info:
        response['return_code'] = process_info['return_code']
    
    if 'end_time' in process_info:
        response['end_time'] = process_info['end_time']
        response['duration'] = process_info['end_time'] - process_info['start_time']
    
    return jsonify(response)

def parse_cql_schema(cql_schema):
    """Parse CQL schema to extract table information"""
    tables = []
    table_regex = re.compile(
        r'CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?(?:(\w+)\.)?(\w+)\s*\(([\s\S]*?)\)\s*(?:WITH\s+[\s\S]*?(?:;|$)|;|$)',
        re.IGNORECASE
    )
    column_regex = re.compile(r'\s*(\w+)\s+([^,)]+)(?:,|$)')
    
    for match in table_regex.finditer(cql_schema):
        keyspace = match.group(1) or None
        table_name = match.group(2)
        columns_text = match.group(3)
        
        columns = []
        for col_match in column_regex.finditer(columns_text):
            col_name = col_match.group(1)
            col_type = col_match.group(2).strip()
            
            # Skip PRIMARY KEY definition for now
            if col_name.lower() == 'primary':
                continue
            
            columns.append({
                'name': col_name,
                'type': col_type
            })
        
        # Extract primary key information
        pk_regex = re.compile(r'PRIMARY\s+KEY\s*\(\s*((?:[\w\s,]+|\([^)]*\))+)\s*\)', re.IGNORECASE)
        pk_match = pk_regex.search(columns_text)
        primary_key = None
        
        if pk_match:
            primary_key = pk_match.group(1).replace('\n', '').replace('\r', '').replace(' ', '')
        
        tables.append({
            'keyspace': keyspace,
            'name': table_name,
            'columns': columns,
            'primary_key': primary_key
        })
    
    return tables

def generate_yaml_files(keyspace_name, tables, num_cycles, threads_option):
    """Generate YAML files for NoSQLBench"""
    yaml_files = {}
    
    for table in tables:
        # Generate schema block
        schema_block = generate_schema_block(keyspace_name, table)
        
        # Generate bindings
        bindings = generate_bindings(table['columns'])
        
        # Generate rampup (data insertion) block
        rampup_block = generate_rampup_block(keyspace_name, table)
        
        # Combine into full YAML with the correct structure
        yaml_content = {
            'scenarios': {
                'default': {
                    'schema1': f"run driver=cql tags=block:\"schema.*\" threads===UNDEF cycles==UNDEF",
                    'rampup1': f"run driver=cql tags='block:rampup1' cycles===TEMPLATE(rampup-cycles,{num_cycles}) threads={threads_option}"
                }
            },
            'bindings': bindings,
            'blocks': {
                'schema1': {
                    'params': {
                        'prepared': False
                    },
                    'ops': schema_block
                },
                'rampup1': {
                    'params': {
                        'cl': 'TEMPLATE(write_cl,LOCAL_QUORUM)',
                        'instrument': True,
                        'prepared': True
                    },
                    'ops': rampup_block
                }
            }
        }
        
        # Convert to YAML string
        yaml_string = yaml.dump(yaml_content, default_flow_style=False, sort_keys=False)
        
        # Create file ID and name
        file_id = f"{table['name']}_{int(time.time())}"
        file_name = f"{table['name']}.yaml"
        file_path = os.path.join(YAML_DIR, f"{file_id}.yaml")
        
        # Save the YAML file
        with open(file_path, 'w') as f:
            f.write(yaml_string)
        
        # Also save with just the table name for easier access
        simple_path = os.path.join(YAML_DIR, f"{table['name']}.yaml")
        with open(simple_path, 'w') as f:
            f.write(yaml_string)
        
        # Store file info
        yaml_files[file_id] = {
            'id': file_id,
            'name': file_name,
            'path': file_path,
            'content': yaml_string
        }
    
    return yaml_files
@app.route('/api/update-yaml', methods=['POST'])
def update_yaml():
    """Update the content of a YAML file"""
    data = request.json
    yaml_id = data.get('yaml_id', '')
    content = data.get('content', '')
    
    if not yaml_id:
        return jsonify({'success': False, 'error': 'No YAML ID provided'}), 400
    
    if not content:
        return jsonify({'success': False, 'error': 'No content provided'}), 400
    
    # Find the YAML file
    yaml_path = None
    for filename in os.listdir(YAML_DIR):
        if filename.endswith('.yaml'):
            if filename == f"{yaml_id}.yaml" or filename.startswith(f"{yaml_id}_"):
                yaml_path = os.path.join(YAML_DIR, filename)
                break
    
    if not yaml_path:
        return jsonify({'success': False, 'error': 'YAML file not found'}), 404
    
    try:
        # Save the updated content
        with open(yaml_path, 'w') as f:
            f.write(content)
        
        # If there's also a simple version with just the table name, update that too
        if '_' in yaml_id:
            table_name = yaml_id.split('_')[0]
            simple_path = os.path.join(YAML_DIR, f"{table_name}.yaml")
            if os.path.exists(simple_path):
                with open(simple_path, 'w') as f:
                    f.write(content)
        
        return jsonify({'success': True})
    except Exception as e:
        logger.error(f"Error updating YAML: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500
    
def generate_schema_block(keyspace_name, table):
    """Generate schema block for creating tables"""
    create_table_statement = f"""CREATE TABLE if not exists <<keyspace:{keyspace_name}>>.{table['name']} (
{generate_column_definitions(table)}
) WITH CLUSTERING ORDER BY (insertedtimestamp DESC);"""
    
    return {
        'create_table1': create_table_statement
    }

def generate_column_definitions(table):
    """Generate column definitions for CREATE TABLE statement"""
    column_lines = []
    for col in table['columns']:
        # Map text type to uuid for specific columns based on the example
        col_type = col['type']
        if col['name'] in ['sessionid', 'requesttype'] and col_type.lower() == 'text':
            col_type = 'uuid'
        column_lines.append(f"{col['name']} {col_type}")
    
    # Add primary key if present
    if table['primary_key']:
        column_lines.append(f"PRIMARY KEY ({table['primary_key']})")
    
    return ',\n'.join(column_lines)

def generate_bindings(columns):
    """Generate bindings for data generation"""
    bindings = {}
    
    binding_map = {
        'sessionid': 'ToHashedUUID()',
        'text': 'AlphaNumericString(10)',
        'varchar': 'AlphaNumericString(10)',
        'int': 'Add(1); ToInt()',
        'bigint': 'Add(1); ToBigInt()',
        'double': 'Add(1.0); ToDouble()',
        'float': 'Add(1.0); ToFloat()',
        'boolean': 'AddCycleRange(0,1); ToBoolean()',
        'decimal': 'Add(1.0); ToBigDecimal()',
        'timestamp': "AddHashRange(0,2419200000L); StartingEpochMillis('2025-01-01 05:00:00'); ToJavaInstant()",
        'date': "StartingEpochMillis('2025-01-01 05:00:00'); ToDate()",
        'time': "StartingEpochMillis('2025-01-01 05:00:00'); ToTime()",
        'uuid': 'ToHashedUUID()',
        'timeuuid': 'ToTimeUUID()',
        'blob': 'RandomBytes(16)'
    }
    
    for col in columns:
        col_name = col['name']
        # Special case for specific column names
        if col_name in binding_map:
            bindings[col_name] = binding_map[col_name]
        else:
            # Extract base type
            base_type = col['type'].lower().split()[0]
            binding = binding_map.get(base_type, 'AlphaNumericString(10)')
            bindings[col_name] = binding
    
    return bindings

def generate_rampup_block(keyspace_name, table):
    """Generate rampup block for data insertion"""
    column_names = [col['name'] for col in table['columns']]
    columns_list = ',\n'.join(column_names)
    values_list = ',\n'.join([f"{{{col}}}" for col in column_names])
    
    insert_statement = f"""insert into <<keyspace:{keyspace_name}>>.{table['name']} (
{columns_list}
) values 
(
{values_list}
);"""
    
    return {
        'insert_rampup1': insert_statement
    }

if __name__ == '__main__':
    # Verify that NoSQLBench JAR exists
    if not os.path.exists(NB_JAR_PATH):
        logger.warning(f"NoSQLBench JAR not found at {NB_JAR_PATH}. Attempting to download...")
        try:
            import urllib.request
            url = "https://github.com/nosqlbench/nosqlbench/releases/download/5.17.3/nb5.jar"
            urllib.request.urlretrieve(url, NB_JAR_PATH)
            logger.info(f"Downloaded NoSQLBench JAR to {NB_JAR_PATH}")
        except Exception as e:
            logger.error(f"Failed to download NoSQLBench JAR: {str(e)}")
            logger.error("Please download it manually from https://github.com/nosqlbench/nosqlbench/releases")
    
    # Run the Flask application
    port = int(os.environ.get('PORT', 5005))
    print(f"Starting NoSQLBench YAML Generator on port {port}...")
    print(f"Access the web interface at http://localhost:{port}")
    app.run(host='0.0.0.0', port=port, debug=True)