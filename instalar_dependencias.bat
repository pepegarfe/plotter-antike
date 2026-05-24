@echo off
echo ================================================
echo  Instalando dependencias del Plotter Antike
echo ================================================
echo.
pip install pyserial svgpathtools ezdxf "pdfminer.six"
echo.
echo ================================================
echo  Listo. Ejecuta: python plotter_control.py
echo ================================================
pause
