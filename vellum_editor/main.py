import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.chdir(os.path.dirname(os.path.abspath(__file__)))

from core.app import VellumTool

if __name__ == "__main__":
    app = VellumTool()
    app.mainloop()
