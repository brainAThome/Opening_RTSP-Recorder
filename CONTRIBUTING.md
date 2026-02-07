# Contributing to RTSP Recorder

First off, thank you for considering contributing to RTSP Recorder! 🎉

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
- [How to Contribute](#how-to-contribute)
- [Development Setup](#development-setup)
- [Coding Guidelines](#coding-guidelines)
- [Submitting Changes](#submitting-changes)
- [Reporting Bugs](#reporting-bugs)
- [Suggesting Features](#suggesting-features)

## Code of Conduct

This project adheres to a [Code of Conduct](CODE_OF_CONDUCT.md). By participating, you are expected to uphold this code.

## Getting Started

1. Fork the repository
2. Clone your fork: `git clone https://github.com/YOUR_USERNAME/Opening_RTSP-Recorder.git`
3. Create a branch for your changes: `git checkout -b feature/your-feature-name`

## How to Contribute

### Types of Contributions

- 🐛 **Bug Fixes** - Fix issues and improve stability
- ✨ **New Features** - Add new functionality
- 📖 **Documentation** - Improve or translate documentation
- 🌍 **Translations** - Add new language support
- 🧪 **Testing** - Add or improve tests
- 🎨 **UI/UX** - Improve the user interface

## Development Setup

### Prerequisites

- Home Assistant 2024.1.0 or later
- Python 3.11+
- Node.js (for frontend development)
- FFmpeg

### Installation for Development

1. Copy the `custom_components/rtsp_recorder` folder to your HA `custom_components` directory
2. Restart Home Assistant
3. Enable debug logging in `configuration.yaml`:

```yaml
logger:
  default: info
  logs:
    custom_components.rtsp_recorder: debug
```

### Running Tests

```bash
# Python tests
pytest tests/

# Linting
flake8 custom_components/rtsp_recorder/
mypy custom_components/rtsp_recorder/
```

## Coding Guidelines

### Python

- **Type Hints**: All functions must have return type annotations (currently 100% coverage!)
- **Docstrings**: Use Google-style docstrings for public functions
- **Formatting**: Follow PEP 8 guidelines
- **Naming**: Use descriptive variable and function names
- **Error Handling**: No silent `except: pass` - always log errors

```python
# Good ✅
async def analyze_frame(frame: np.ndarray, camera: str) -> AnalysisResult:
    """Analyze a video frame for person detection.
    
    Args:
        frame: The video frame as numpy array
        camera: Camera identifier
        
    Returns:
        AnalysisResult with detected persons
    """
    try:
        result = await self._detector.detect(frame)
        return result
    except Exception as e:
        _LOGGER.debug("Frame analysis failed: %s", e)
        return AnalysisResult.empty()

# Bad ❌
def analyze(f, c):
    try:
        return detector.detect(f)
    except:
        pass
```

### JavaScript (Frontend)

- Use modern ES6+ syntax
- Document complex functions
- Use meaningful variable names
- Follow existing code style

### Commit Messages

Use conventional commit format:

```
type(scope): description

[optional body]

[optional footer]
```

**Types:**
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation changes
- `style`: Code style changes (formatting, etc.)
- `refactor`: Code refactoring
- `test`: Adding or updating tests
- `chore`: Maintenance tasks

**Examples:**
```
feat(detection): add support for multiple TPU devices
fix(recording): resolve memory leak in long recordings
docs(readme): update installation instructions
```

## Submitting Changes

1. Ensure your code follows the coding guidelines
2. Add/update tests if applicable
3. Update documentation if needed
4. Run linting and tests locally
5. Push your branch and create a Pull Request
6. Fill out the PR template completely
7. Wait for review - respond to feedback promptly

### Pull Request Checklist

- [ ] Code follows project coding guidelines
- [ ] Type hints added for new functions
- [ ] Tests added/updated
- [ ] Documentation updated
- [ ] CHANGELOG.md updated
- [ ] No linting errors
- [ ] Tested in Home Assistant

## Reporting Bugs

Before reporting a bug:

1. Check existing issues to avoid duplicates
2. Update to the latest version
3. Collect relevant logs and information

When reporting, include:

- RTSP Recorder version
- Home Assistant version
- Python version
- Hardware (especially TPU details)
- Steps to reproduce
- Expected vs actual behavior
- Relevant log entries

## Suggesting Features

Feature requests are welcome! Please:

1. Check existing issues/discussions first
2. Describe the problem you're trying to solve
3. Explain your proposed solution
4. Consider potential impact on existing users

## Questions?

Feel free to:
- Open a Discussion on GitHub
- Check the [User Guide](docs/USER_GUIDE.md)
- Review the [FAQ](docs/TROUBLESHOOTING.md)

---

Thank you for contributing! 🙏
