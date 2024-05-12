# Használj egy hivatalos Python runtime-t alapként
FROM python:3.10

# Frissítsd a rendszercsomagokat és telepítsd a szükséges függőségeket
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       libopencv-dev \
       libgl1-mesa-glx \
    && rm -rf /var/lib/apt/lists/*

# Állítsd be a munkakönyvtárat a konténerben
WORKDIR /app

# Másold a függőségeket és telepítsd őket
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Másold a jelenlegi könyvtár tartalmát a konténer /app könyvtárába
COPY . /app

# Exponáld az alkalmazás portját
EXPOSE 5000

# Futásd az alkalmazást, ha a konténer elindul
CMD ["python", "app.py"]