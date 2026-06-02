use tauri::Manager;
use std::net::TcpStream;
use std::process::{Child, Command};
use std::sync::{Mutex, OnceLock};
use std::time::Duration;

static BACKEND_CHILD: OnceLock<Mutex<Option<Child>>> = OnceLock::new();

fn backend_child() -> &'static Mutex<Option<Child>> {
    BACKEND_CHILD.get_or_init(|| Mutex::new(None))
}

fn is_backend_running() -> bool {
    // Quickly verify if the backend API server is actively listening on its port
    TcpStream::connect_timeout(
        &"127.0.0.1:8008".parse().unwrap(),
        Duration::from_millis(500),
    )
    .is_ok()
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

fn start_backend(app: &tauri::AppHandle) {
    // Purge orphaned backend instances to ensure a clean state and prevent deadlocks
    if is_backend_running() {
        println!("Detected existing backend on port 8008 — killing zombie session...");
        kill_backend_port(8008);
        std::thread::sleep(Duration::from_millis(500));
    }

    println!("Starting Ember backend...");

    let resource_dir = app
        .path()
        .resource_dir()
        .expect("Failed to get resource directory");

    let backend_path = resource_dir
        .join("_up_")
        .join("_up_")
        .join("dist")
        .join("ember-backend");

    let child = Command::new(&backend_path)
        .spawn()
        .expect("Failed to start backend");

    *backend_child().lock().unwrap() = Some(child);

    let mut started = false;
    for _ in 0..20 {
        if is_backend_running() {
            println!("Backend ready!");
            started = true;
            break;
        }
        std::thread::sleep(Duration::from_millis(500));
    }

    if !started {
        println!("Backend did not become ready after 10 seconds.");
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

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let app = tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .setup(|app| {
            start_backend(app.handle());
            Ok(())
        })
        .run(tauri::generate_context!());

    stop_backend();

    app.expect("error while running tauri application");
}