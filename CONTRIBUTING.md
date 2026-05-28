# Contributing to qr-transfer

## Local Setup

1. Clone the repository:
   ```bash
   git clone https://github.com/marco-ragusa/qr-transfer.git
   cd qr-transfer
   ```

2. Create and activate a virtual environment:

   **Windows:**
   ```bash
   python -m venv venv
   venv\Scripts\activate
   ```
   **Linux/macOS:**
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt -r requirements-dev.txt
   ```

## Running Tests

From the repo root (venv active):
```bash
pytest
```

For verbose output:
```bash
pytest -v
```

## Commit Convention

This project uses [Conventional Commits](https://www.conventionalcommits.org/):

| Prefix | When to use |
|--------|------------|
| `feat:` | New feature |
| `fix:` | Bug fix |
| `docs:` | Documentation only |
| `refactor:` | Code restructure, no behavior change |
| `test:` | Adding or updating tests |
| `chore:` | Maintenance, tooling, config |

## Pull Request Process

1. Fork the repository
2. Create a feature branch: `git checkout -b feat/my-feature`
3. Commit your changes following the convention above
4. Push and open a Pull Request against `main`
5. Fill in the PR template
