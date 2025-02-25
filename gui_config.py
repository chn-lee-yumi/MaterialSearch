# 使用Tkinter创建GUI，用于配置参数
# 启动时读取配置文件（.env），将内容显示在窗口中
# 窗口包含一个多行文本框，用于显示和修改参数，下方有一个按钮，点击按钮后将文本框中的内容写入配置文件，并启动main.py
# TODO: windows测试，打包后配置文件和数据库路径问题
import tkinter as tk
from tkinter import scrolledtext
import os
import sys

def load_file_content(filepath):
    """Reads file content; returns an empty string if the file doesn't exist."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return f.read()
    except FileNotFoundError:
        return ""

def save_file_content(filepath, content):
    """Writes content to the file."""
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)

def run_main():
    """Runs main.py and exits the current script."""
    filepath = ".env"
    new_content = text_area.get("1.0", tk.END)
    save_file_content(filepath, new_content)

    root.destroy()
    root.quit()
    os.execv(sys.executable, [sys.executable, "main.py"] + sys.argv[1:])


def create_gui():
    """Creates the GUI window."""

    filepath = ".env"  # File path
    global text_area, root  # Declare text_area as global

    root = tk.Tk()
    root.title("配置修改 / Config Editor")

    # Multiline text box
    text_area = scrolledtext.ScrolledText(root, wrap=tk.WORD, width=150, height=30)
    text_area.pack(padx=10, pady=10)

    # Load file content
    content = load_file_content(filepath)
    text_area.insert(tk.INSERT, content)

    # Save and run button (modified command)
    save_button = tk.Button(root, text="保存并启动 / Save and Run", command=run_main)
    save_button.pack(pady=10)

    root.mainloop()

if __name__ == "__main__":
    create_gui()