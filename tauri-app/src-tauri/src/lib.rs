#![allow(unused_imports)]
use tauri::Manager;
use std::net::TcpStream;
use std::process::{Child, Command};
use std::sync::{Mutex, OnceLock};
use std::time::Duration;

static BACKEND_CHILD: OnceLock<Mutex<Option<Child>>> = OnceLock::new();

fn backend_child() -> &'static Mutex<Option<Child>> {
    BACKEND_CHILD.get_or_init(|| Mutex::new(None))
}

fn is_port_in_use() -> bool {
    // Quickly verify if the backend API server is actively listening on its port
    TcpStream::connect_timeout(
        &"127.0.0.1:8008".parse().unwrap(),
        Duration::from_millis(500),
    )
    .is_ok()
}

fn is_backend_ready() -> bool {
    use std::io::{Write, Read};
    if let Ok(mut stream) = TcpStream::connect_timeout(
        &"127.0.0.1:8008".parse().unwrap(),
        Duration::from_millis(500),
    ) {
        if stream.write_all(b"GET /health HTTP/1.0\r\n\r\n").is_ok() {
            let mut response = String::new();
            if stream.read_to_string(&mut response).is_ok() {
                return response.contains("200 OK");
            }
        }
    }
    false
}


fn find_backend_pids(port: u16) -> Vec<u32> {
    let mut pids = Vec::new();

    // Use OS-specific networking commands to resolve process IDs holding the local port
    #[cfg(target_os = "windows")]
    {
        if let Ok(output) = Command::new("cmd")
            .args([
                "/C",
                &format!("netstat -ano | findstr :{}", port),
            ])
            .output()
        {
            if output.status.success() {
                let text = String::from_utf8_lossy(&output.stdout);
                for line in text.lines() {
                    if line.contains("LISTENING") {
                        if let Some(pid_str) = line.split_whitespace().last() {
                            if let Ok(pid) = pid_str.trim().parse() {
                                pids.push(pid);
                            }
                        }
                    }
                }
            }
        }
    }

    #[cfg(not(target_os = "windows"))]
    {
        if let Ok(output) = Command::new("ss")
            .arg("-ltnp")
            .arg(format!("sport = :{}", port))
            .output()
        {
            if output.status.success() {
                let text = String::from_utf8_lossy(&output.stdout);
                for line in text.lines().skip(1) {
                    let mut rest = line;
                    while let Some(idx) = rest.find("pid=") {
                        rest = &rest[idx + 4..];
                        let pid: String = rest.chars().take_while(|c| c.is_ascii_digit()).collect();
                        if let Ok(pid) = pid.parse() {
                            pids.push(pid);
                        }
                        if let Some(next_idx) = rest.find("pid=") {
                            rest = &rest[next_idx..];
                        } else {
                            break;
                        }
                    }
                }
            }
        }

        if pids.is_empty() {
            if let Ok(output) = Command::new("lsof")
                .arg("-t")
                .arg(format!("-iTCP:{}", port))
                .arg("-sTCP:LISTEN")
                .arg("-n")
                .output()
            {
                if output.status.success() {
                    let text = String::from_utf8_lossy(&output.stdout);
                    for line in text.lines() {
                        if let Ok(pid) = line.trim().parse() {
                            pids.push(pid);
                        }
                    }
                }
            }
        }
    }

    pids
}

fn kill_backend_port(port: u16) {
    for pid in find_backend_pids(port) {
        #[cfg(target_os = "windows")]
        let _ = Command::new("taskkill")
            .args(["/F", "/PID", &pid.to_string()])
            .status();

        #[cfg(not(target_os = "windows"))]
        let _ = Command::new("kill")
            .arg("-9")
            .arg(pid.to_string())
            .status();
    }
}

#[allow(unused_variables)]
fn start_backend(app: &tauri::AppHandle) {
    println!("Starting Ember backend...");

    #[cfg(debug_assertions)]
    let child = {
        let manifest_dir = std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR"));
        let root_dir = manifest_dir.join("..").join("..");
        
        #[cfg(target_os = "windows")]
        let python_path = root_dir.join(".venv").join("Scripts").join("python.exe");
        #[cfg(not(target_os = "windows"))]
        let python_path = root_dir.join(".venv").join("bin").join("python");

        let server_path = root_dir.join("core").join("api").join("server.py");
        
        println!("[DEV MODE] Spawning raw Python backend...");

        #[cfg(target_os = "windows")]
        {
            use std::os::windows::process::CommandExt;
            const CREATE_NO_WINDOW: u32 = 0x08000000;
            Command::new(python_path)
                .env("PYTHONPATH", &root_dir)
                .arg("-W").arg("ignore")
                .arg(server_path)
                .stdout(std::process::Stdio::inherit())
                .stderr(std::process::Stdio::inherit())
                .creation_flags(CREATE_NO_WINDOW)
                .spawn()
                .expect("Failed to start python backend in dev mode")
        }
        #[cfg(not(target_os = "windows"))]
        Command::new(python_path)
            .env("PYTHONPATH", &root_dir)
            .arg("-W").arg("ignore")
            .arg(server_path)
            .stdout(std::process::Stdio::inherit())
            .stderr(std::process::Stdio::inherit())
            .spawn()
            .expect("Failed to start python backend in dev mode")
    };

    #[cfg(not(debug_assertions))]
    let child = {
        let resource_dir = app
            .path()
            .resource_dir()
            .expect("Failed to get resource directory");

        #[cfg(not(target_os = "windows"))]
        let backend_path = resource_dir.join("ember-backend");
        
        #[cfg(target_os = "windows")]
        let backend_path = resource_dir.join("ember-backend.exe");

        println!("[PROD MODE] Spawning compiled sidecar...");

        #[cfg(target_os = "windows")]
        {
            use std::os::windows::process::CommandExt;
            const CREATE_NO_WINDOW: u32 = 0x08000000;
            Command::new(&backend_path)
                .creation_flags(CREATE_NO_WINDOW)
                .spawn()
                .expect("Failed to start bundled backend")
        }
        #[cfg(not(target_os = "windows"))]
        Command::new(&backend_path)
            .spawn()
            .expect("Failed to start bundled backend")
    };

    *backend_child().lock().unwrap() = Some(child);

    let mut started = false;
    for _ in 0..120 {
        if is_backend_ready() {
            println!("Backend ready!");
            started = true;
            break;
        }
        std::thread::sleep(Duration::from_millis(500));
    }

    if !started {
        println!("Backend did not become ready after 60 seconds.");
    }
}

fn stop_backend() {
    let mut guard = backend_child().lock().unwrap();

    if let Some(mut child) = guard.take() {
        if child.kill().is_ok() {
            let _ = child.wait();
        }
    }
}

#[tauri::command]
async fn init_backend(app: tauri::AppHandle) -> Result<(), String> {
    let guard = BACKEND_CHILD.get_or_init(|| Mutex::new(None)).lock().unwrap();
    if guard.is_some() {
        return Ok(());
    }
    drop(guard);
    
    // Purge orphaned backend instances synchronously so frontend waits
    if is_port_in_use() {
        println!("Detected existing backend on port 8008 — killing zombie session...");
        kill_backend_port(8008);
        
        // Wait for the OS to actually free the port
        for _ in 0..10 {
            if !is_port_in_use() {
                break;
            }
            std::thread::sleep(Duration::from_millis(500));
        }
    }
    
    std::thread::spawn(move || {
        start_backend(&app);
    });
    
    Ok(())
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .invoke_handler(tauri::generate_handler![init_backend])
        .on_window_event(|_window, event| {
            if let tauri::WindowEvent::Destroyed = event {
                stop_backend();
            }
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}