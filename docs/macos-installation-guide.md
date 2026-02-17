# macOS Installation Guide

This guide will help you set up your macOS development environment to run CartPilot locally.

## Prerequisites Checklist

Before starting, ensure you have:
- macOS 10.15 (Catalina) or later
- Administrator access to install software
- Internet connection for downloading packages

## Required Software

### 1. Homebrew (Package Manager)

Homebrew is the recommended package manager for macOS. It simplifies installing development tools and dependencies.

**Installation:**
```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

**Verify installation:**
```bash
brew --version
```

**Expected output:**
```
Homebrew 4.x.x
```

**Note:** After installation, you may need to add Homebrew to your PATH. Follow the instructions shown in the terminal output.

---

### 2. Docker Desktop for macOS

Docker Desktop provides the Docker engine, Docker Compose, and a GUI for managing containers on macOS.

**Installation:**
```bash
brew install --cask docker
```

**Alternative:** Download from [Docker Desktop website](https://www.docker.com/products/docker-desktop/)

**Start Docker Desktop:**
```bash
open -a Docker
```

**Verify installation:**
```bash
docker --version
docker compose version
```

**Expected output:**
```
Docker version 24.x.x, build xxxxx
Docker Compose version v2.x.x
```

**Important:** Docker Desktop must be running before using `docker compose` commands. The Docker icon should appear in your menu bar.

---

### 3. Git (Version Control)

Git is required to clone the repository and manage code versions.

**Installation:**
```bash
brew install git
```

**Verify installation:**
```bash
git --version
```

**Expected output:**
```
git version 2.x.x
```

**Configure Git (if not already done):**
```bash
git config --global user.name "Your Name"
git config --global user.email "your.email@example.com"
```

---

### 4. Python 3.11+ (Optional - for Local Development)

Python is required if you want to run CartPilot services locally without Docker, or for running tests and development tools.

**Installation:**
```bash
brew install python@3.11
```

**Verify installation:**
```bash
python3 --version
```

**Expected output:**
```
Python 3.11.x
```

**Create symlink (optional, for easier access):**
```bash
brew link python@3.11
```

**Note:** If you only plan to use Docker Compose, Python installation is optional.

---

### 5. Command Line Tools (Xcode Command Line Tools)

Required for compiling Python packages and other development tools.

**Installation:**
```bash
xcode-select --install
```

**Verify installation:**
```bash
xcode-select -p
```

**Expected output:**
```
/Library/Developer/CommandLineTools
```

**Note:** This may prompt you to install Xcode Command Line Tools. Click "Install" if prompted.

---

## Optional Development Tools

### 6. jq (JSON Processor)

Useful for parsing JSON responses in shell scripts and testing.

**Installation:**
```bash
brew install jq
```

**Verify installation:**
```bash
jq --version
```
**Expected output:**
```
jq-1.8.1
```

---

### 7. curl (HTTP Client)

Usually pre-installed on macOS, but verify it's available.

**Verify installation:**
```bash
curl --version
```

**If not installed:**
```bash
brew install curl
```

---

## Verification Steps

After installing all components, verify your setup:

### 1. Check Docker is Running

```bash
docker info
```

Should show Docker system information without errors.

### 2. Test Docker Compose

```bash
docker compose version
```

Should display Docker Compose version.

### 3. Check Python (if installed)

```bash
python3 --version
# or
python3.11 --version
```

Should show Python 3.11 or later.

### 4. Verify Git

```bash
git --version
```

Should display Git version.

---

## Quick Start After Installation

Once all prerequisites are installed:

### 1. Clone the Repository

```bash
git clone <repository-url>
cd cart-pilot
```

### 2. Start CartPilot with Docker Compose

```bash
# Start all services
docker compose up

# Or run in background
docker compose up -d

# View logs
docker compose logs -f cartpilot-api
```

### 3. Verify Services are Running

```bash
# Check health endpoints
curl http://localhost:8000/health  # CartPilot API
curl http://localhost:8001/health  # Merchant A
curl http://localhost:8002/health  # Merchant B
curl http://localhost:8003/health  # MCP Server
```

---

## Troubleshooting

### Docker Desktop Not Starting

**Issue:** Docker Desktop fails to start or shows errors.

**Solutions:**
1. Ensure you have enough disk space (Docker requires several GB)
2. Check System Preferences > Security & Privacy for Docker permissions
3. Restart your Mac if Docker was recently installed
4. Reinstall Docker Desktop:
   ```bash
   brew uninstall --cask docker
   brew install --cask docker
   ```

### Port Already in Use

**Issue:** Error message about ports 8000, 8001, 8002, 8003, or 5432 being in use.

**Solution:**
```bash
# Check what's using the port
lsof -i :8000

# Stop the process or change ports in docker-compose.yml
```

### Python Version Issues

**Issue:** Wrong Python version or `python3` command not found.

**Solution:**
```bash
# Check installed Python versions
brew list | grep python

# Use specific version
python3.11 --version

# Create alias in ~/.zshrc or ~/.bash_profile
echo 'alias python3=python3.11' >> ~/.zshrc
source ~/.zshrc
```

### Homebrew Installation Issues

**Issue:** Homebrew installation fails or commands not found.

**Solution:**
1. Check if Homebrew is in PATH:
   ```bash
   echo $PATH | grep -o '/opt/homebrew/bin\|/usr/local/bin'
   ```

2. Add to PATH (for Apple Silicon Macs):
   ```bash
   echo 'eval "$(/opt/homebrew/bin/brew shellenv)"' >> ~/.zshrc
   source ~/.zshrc
   ```

3. For Intel Macs:
   ```bash
   echo 'eval "$(/usr/local/bin/brew shellenv)"' >> ~/.zshrc
   source ~/.zshrc
   ```

### Docker Compose Permission Issues

**Issue:** Permission denied errors when running Docker commands.

**Solution:**
1. Ensure Docker Desktop is running
2. Add your user to docker group (if applicable):
   ```bash
   sudo dseditgroup -o edit -a $(whoami) -t user _docker
   ```
3. Restart Docker Desktop

---

## System Requirements

### Minimum Requirements

- **macOS:** 10.15 (Catalina) or later
- **RAM:** 8 GB (16 GB recommended)
- **Disk Space:** 20 GB free space
- **CPU:** Intel or Apple Silicon (M1/M2/M3)

### Recommended Requirements

- **macOS:** 12.0 (Monterey) or later
- **RAM:** 16 GB
- **Disk Space:** 50 GB free space
- **CPU:** Apple Silicon (M1/M2/M3) for better performance

---

## Next Steps

After completing the installation:

1. **Read the main README:** See `README.md` for project overview
2. **Review Quick Start:** Follow the Quick Start section in README
3. **Explore Documentation:** Check `docs/` directory for detailed guides
4. **Run Demo Scripts:** Try `scripts/demo_happy_path.sh` to see CartPilot in action

---

## Additional Resources

- [Homebrew Documentation](https://docs.brew.sh/)
- [Docker Desktop for Mac Documentation](https://docs.docker.com/desktop/install/mac-install/)
- [Python Documentation](https://www.python.org/docs/)
- [Git Documentation](https://git-scm.com/doc)

---

## Support

If you encounter issues not covered in this guide:

1. Check the main `README.md` for troubleshooting
2. Review `deploy/LOCAL_COMPATIBILITY.md` for Docker-specific issues
3. Check Docker logs: `docker compose logs <service-name>`
4. Verify all services are healthy: `docker compose ps`
