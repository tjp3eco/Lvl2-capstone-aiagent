# Ollama Installation Guide

Complete installation instructions for Windows, macOS, and Linux.

---

## Windows Installation

### Method 1: Official Installer (Recommended)

1. **Download**: Visit https://ollama.com/download and download the Windows installer
2. **Run**: Double-click `OllamaSetup.exe`
3. **Follow prompts**: Accept defaults, install
4. **Complete**: Ollama will run automatically in the system tray

### Method 2: Winget (Package Manager)

```powershell
winget install Ollama.Ollama
```

### Method 3: Chocolatey

```powershell
choco install ollama
```

### Verify Windows Installation

```powershell
# In PowerShell or Command Prompt
ollama --version

# Should show: ollama version 0.x.x

# Test the API
curl http://localhost:11434/api/tags
```

### Windows Notes

- **System Tray**: Ollama runs in the background (look for llama icon in system tray)
- **Data Location**: Models stored in `C:\Users\<username>\.ollama`
- **RAM Requirements**:
  - 4GB RAM minimum for 3B models
  - 8GB RAM for 7B models
  - 16GB+ RAM for 13B+ models
- **GPU**: Optional (CUDA acceleration on NVIDIA GPUs)

---

## macOS Installation

### Method 1: Official Installer (Recommended)

1. **Download**: Visit https://ollama.com/download and download the macOS app
2. **Install**: Drag `Ollama.app` to your Applications folder
3. **Launch**: Open from Applications or Spotlight
4. **Allow**: Grant permissions if prompted (for downloads/models)

### Method 2: Homebrew

```bash
# Install Homebrew first if you don't have it
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Install Ollama
brew install --cask ollama
```

### Verify macOS Installation

```bash
# In Terminal
ollama --version

# Test the API
curl http://localhost:11434/api/tags
```

### macOS Notes

- **Menu Bar**: Ollama runs from the menu bar (llama icon)
- **Data Location**: `~/.ollama`
- **Apple Silicon**: Optimized for M1/M2/M3 (uses GPU)
- **Intel Mac**: Supported but no GPU acceleration
- **RAM**: Same requirements as Windows

---

## Linux Installation

### Method 1: Official Install Script (Recommended)

```bash
# Install with one command
curl -fsSL https://ollama.com/install.sh | sh

# Or with sudo if needed
curl -fsSL https://ollama.com/install.sh | sudo sh
```

### Method 2: Manual Installation

**For AMD64/x86_64:**
```bash
# Download and extract
curl -L https://ollama.com/download/ollama-linux-amd64.tgz -o ollama-linux-amd64.tgz
sudo tar -xzf ollama-linux-amd64.tgz -C /usr/local/bin

# Create systemd service
sudo useradd -r -s /bin/false -U -m -d /usr/share/ollama ollama
sudo usermod -a -G ollama $(whoami)

# Create service file
sudo tee /etc/systemd/system/ollama.service > /dev/null <<EOF
[Unit]
Description=Ollama Service
After=network-online.target

[Service]
ExecStart=/usr/local/bin/ollama serve
User=ollama
Group=ollama
Restart=always
RestartSec=3

[Install]
WantedBy=default.target
EOF

# Start service
sudo systemctl daemon-reload
sudo systemctl enable ollama
sudo systemctl start ollama
```

### Method 3: Docker

```bash
# Run Ollama in Docker
docker run -d -v ollama:/root/.ollama -p 11434:11434 --name ollama ollama/ollama

# Interact with container
docker exec -it ollama ollama run llama3.2
```

### Verify Linux Installation

```bash
# Check version
ollama --version

# Test API
curl http://localhost:11434/api/tags

# Check service status (if using systemd)
sudo systemctl status ollama
```

### Linux Notes

- **Service**: Runs as systemd service on most distributions
- **Data Location**: `/usr/share/ollama` or `~/.ollama`
- **GPU Support**: CUDA for NVIDIA, ROCm for AMD (manual setup required)
- **Permissions**: Add your user to the `ollama` group: `sudo usermod -a -G ollama $(whoami)`

---

## Pulling Models

Once Ollama is installed, you need to download models:

### Recommended Starter Models

```bash
# Small and fast (3B parameters)
ollama pull llama3.2:3b

# Good balance (7B parameters)
ollama pull mistral:7b
ollama pull llama3.1:8b
ollama pull qwen2.5:7b

# Larger models (13B+)
ollama pull llama3.1:70b  # Requires 64GB+ RAM
```

### Model Size Reference

| Model | RAM Required | Speed | Quality |
|-------|--------------|-------|---------|
| 3B | 4-6GB | Fast | Basic |
| 7B | 8-10GB | Medium | Good |
| 13B | 16-20GB | Slower | Better |
| 70B | 64GB+ | Slow | Best |

### Running Models

```bash
# Interactive chat
ollama run mistral:7b

# Single prompt
ollama run mistral:7b "What is machine learning?"

# Run another model
ollama run llama3.2:3b
```

---

## Testing Ollama

### Quick Tests

```bash
# Check if Ollama is running
curl http://localhost:11434

# Should return: Ollama is running

# List local models
curl http://localhost:11434/api/tags

# Test generation
curl -X POST http://localhost:11434/api/generate -d '{
  "model": "mistral:7b",
  "prompt": "Hello, how are you?"
}'

# Test chat API
curl -X POST http://localhost:11434/api/chat -d '{
  "model": "mistral:7b",
  "messages": [{"role": "user", "content": "Hello!"}]
}'
```

### Python Test Script

Create `test_ollama.py`:

```python
import requests
import json

def test_ollama():
    # Test connection
    try:
        r = requests.get("http://localhost:11434")
        print("✓ Ollama is running")
    except:
        print("✗ Ollama is not running. Start it with: ollama serve")
        return

    # Test model availability
    r = requests.get("http://localhost:11434/api/tags")
    models = r.json().get("models", [])
    print(f"✓ Available models: {[m['name'] for m in models]}")

    # Test generation if mistral is available
    if any("mistral" in m['name'] for m in models):
        print("\n✓ Testing generation with mistral...")
        r = requests.post(
            "http://localhost:11434/api/generate",
            json={"model": "mistral:7b", "prompt": "Say hello in one word:", "stream": False}
        )
        print(f"Response: {r.json().get('response', 'No response')}")

if __name__ == "__main__":
    test_ollama()
```

Run: `python test_ollama.py`

---

## Troubleshooting

### Port Already in Use

```bash
# Find process using port 11434
# Windows
netstat -ano | findstr :11434
taskkill /PID <PID> /F

# macOS/Linux
lsof -i :11434
kill -9 <PID>
```

### Model Download Fails

```bash
# Try with explicit model name
ollama pull mistral:7b

# Check internet connection
ping ollama.com

# Try alternate DNS
# On Windows: Use Google DNS (8.8.8.8) or Cloudflare (1.1.1.1)
```

### Out of Memory

```bash
# Use smaller model
ollama run llama3.2:3b  # 3B parameters, ~4GB RAM

# Quantized models are smaller
ollama run mistral:7b-q4  # 4-bit quantization
```

### GPU Not Detected

**NVIDIA (CUDA):**
```bash
# Check CUDA is installed
nvidia-smi

# Install CUDA toolkit if needed
# https://developer.nvidia.com/cuda-downloads
```

**AMD (ROCm):**
- ROCm support is experimental on Linux only
- Check Ollama documentation for latest AMD support

**Apple Silicon (MPS):**
- Should work automatically on M1/M2/M3
- Check Activity Monitor for GPU usage

---

## Quick Reference Card

### Common Commands

```bash
# Start/stop service
ollama serve              # Start server
ollama --version          # Check version

# Model management
ollama pull <model>       # Download model
ollama rm <model>         # Remove model
ollama list               # List local models
ollama run <model>        # Interactive chat

# API endpoints
curl http://localhost:11434/api/tags      # List models
curl http://localhost:11434/api/generate  # Generate text
curl http://localhost:11434/api/chat       # Chat completion
```

### Model Recommendations by Use Case

| Use Case | Model | Why |
|----------|-------|-----|
| Fast prototyping | llama3.2:3b | Speed, low resource |
| General purpose | mistral:7b | Good balance |
| Coding tasks | codellama:7b | Optimized for code |
| Following instructions | qwen2.5:7b | Strong instruction following |

---

## Additional Resources

- **Official Ollama**: https://ollama.com
- **GitHub Repo**: https://github.com/ollama/ollama
- **Documentation**: https://github.com/ollama/ollama/blob/main/docs/README.md
- **Model Library**: https://ollama.com/library
- **API Reference**: https://github.com/ollama/ollama/blob/main/docs/api.md

---

Last Updated: April 2025
