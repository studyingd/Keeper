import os

if os.environ.get("KEEPER_UI") == "qml":
    from password_manager.app_qml import main
else:
    from password_manager.app import main


if __name__ == "__main__":
    main()
