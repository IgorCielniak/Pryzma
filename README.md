# Pryzma

<table>
  <tr>
    <td width="220">
      <img src="assets/logo.png" alt="Pryzma Logo" width="280">
    </td>
    <td>
        <strong>Pryzma</strong> is a modern, general-purpose programming language designed to be <strong>powerful</strong>, <strong>consistent</strong>, and <strong>highly extensible</strong>.<br>
        It combines the <strong>simplicity of C</strong>, the <strong>flexibility of Python</strong>, and <strong>metaprogramming capabilities</strong> inspired by systems-level languages — all while remaining lightweight and fast.
    </td>
  </tr>
</table>


## ✨ Features

- 🧠 **Clean and expressive syntax** — Minimal boilerplate, intuitive structure.
- ⚡ **Compiled & Interpreted** — Write scripts quickly or build performant binaries.
- 🧩 **Powerful import system** — Easily split projects into multiple files and modules.
- 🧱 **Rich language features**:
  - Structs with defaults, equality, and optional fields
  - Functions with inferred return types
  - First-class function references
  - Inline assembly support with x86_64 emulation
- 🧰 **Metaprogramming & Preprocessing** — Custom keywords, macros, and code generation.
- 📦 **Built-in package manager (PPM)** — Easily install and manage Pryzma packages.
- 🐚 **System integration** — Inline Python, shell commands, and extended runtime hooks.
- 🧪 **Sandbox & Virtual Environments** — Safe execution and project isolation.
- 🧠 **Customizable REPL** — Inspect functions, evaluate code interactively, and explore the language.

---

## 📁 Project Structure

```
Pryzma/
├─ Pryzma-programming-language/   # Language core and interpreter
├─ tools/                         # universal testing tool and ictfd
├─ pryzmalib/                     # Python library for integration
├─ pryzma_manager.py              # Pryzma manager
├─ plugins/                       # Plugins for pryzma_manager.py
├─ config.json                    # Config for pryzma_manager.py
└─ hellp.pryzma                   # Hello world in Pryzma
```

## 🚀 Getting Started

### 1. Clone the Repository

```bash
git clone https://github.com/IgorCielniak/Pryzma.git
cd Pryzma
```

### 2. Run Your First Script

```bash
cd Pryzma-programming-language #cd in to the language core
python Pryzma.py tests/hello.pryzma
```

or open the REPL:

```bash
python Pryzma.py
```

---

## 🧑‍💻 Example Code

```pryzma
/greet{
    print "Hello, " + args[0] + "!"
}

username = "World"
@greet(username)
```

---

## 📦 Package Management

Pryzma comes with a built-in package manager called **PPM**.

**In the repl:**

```bash
ppm install async
ppm list
ppm remove async
```

---

## 🧠 Advanced Capabilities

- 🧱 **Inline Assembly** — Embed x86_64 instructions directly in your code.
- 🧠 **Preprocessor Directives** — Generate and transform code at run time.
- 🌐 **Inline Python** — Intermix Python for fast prototyping or integration.

---

## 🧰 Official Tools

- `pryzma-manager` — Project & environment management CLI
- `ppm` — Package manager _(buildt in in to both the main interpreter and the manager)_
- `REPL` — Interactive shell in the interpreter with a buildt in interactive debugger

---

## 📜 License

Pryzma is open-source and licensed under the **Apache 2.0 License**.  
See [LICENSE](./LICENSE) for more information.

---

## 🤝 Acknowledgements

- Inspired by the simplicity of C
- Influenced by the flexibility of Python
- With ideas borrowed from Jai and other modern languages.

