from app import app
from flask import render_template, request, redirect, jsonify
import os
import time
import requests
import json
import urllib
from datetime import datetime, timedelta
from math import sin, cos, sqrt, atan2, radians
from bs4 import BeautifulSoup
from pymongo import MongoClient

#TODO Hommaa laivoille uusi marker, joka kääntyy suunnan mukaan.
#TODO Paranna sivuston ulkonäköä 
#TODO Muuta Suomen kielelle myös laivojen tyypit
#TODO JS erilliseen tiedostoon
#TODO jos laivaaa ei ole sulussa niin muuttuja isShip?? Tämän mukaan sitten poistaa kaikki nettisivulta. 

def iso_time():
    current_time = (datetime.utcnow()- timedelta(hours = 0.005)).isoformat().replace(":", "%3A")
    iso_time = current_time[:23] + ".000Z"
    return iso_time

def calculate_distance(lat1,lon1,lat2,lon2):
    # approximate radius of earth in km
    R = 6373.0
    lat1 = radians(lat1)
    lon1 = radians(lon1)
    lat2 = radians(lat2)
    lon2 = radians(lon2)
    dlon = lon2 - lon1
    dlat = lat2 - lat1
    a = sin(dlat / 2)**2 + cos(lat1) * cos(lat2) * sin(dlon / 2)**2
    c = 2 * atan2(sqrt(a), sqrt(1 - a))
    distance = R * c
    return round(distance,2)

def get_ship_type(ship_type_number):
    if 20 < ship_type_number <= 29:
        ship_type = "Wing in ground (WIG)"
    elif (31 <= ship_type_number <= 32):
        ship_type = "Tug (towing)"
    elif ship_type_number == 33:
        ship_type = "Dredging, underwater operations"
    elif ship_type_number == 34:
        ship_type = "Diving operations"
    elif ship_type_number == 35:
        ship_type = "Military"
    elif ship_type_number == 36:
        ship_type = "Sailing"
    elif ship_type_number == 37:
        ship_type = "Pleasure craft"               
    elif 40 <= ship_type_number <= 49:
        ship_type = "High speed craft (HSC)"
    elif ship_type_number == 50:
        ship_type = "Pilot"    
    elif ship_type_number == 51:
        ship_type = "Search and rescue"    
    elif ship_type_number == 52:
        ship_type = "Tug"        
    elif ship_type_number == 53:
        ship_type = "Port tender"        
    elif ship_type_number == 54:
        ship_type = "Anti pollution"        
    elif ship_type_number == 55:
        ship_type = "Law enforcement"               
    elif 60 <= ship_type_number <= 69:
        ship_type = "Passenger"               
    elif 70 <= ship_type_number <= 79:
        ship_type = "Cargo"               
    elif 80 <= ship_type_number <= 89:
        ship_type = "Tanker"
    else:
        ship_type = "Other or unknown type"
    return ship_type

#Returns navigation status in text
def get_nav_status(nav_stat_number):
    nav_statuses ={0:"Under way using engine", 1:"At anchor", 2:"Not under command", 3:"Restricted manoeuverability", 
    4:"Constrained by her draught", 5:"Moored", 6:"Aground", 7:"Engaged in Fishing", 8:"Under way sailing"} 

    try: 
        nav_stat = nav_statuses[nav_stat_number]
    except:
        nav_stat = "Other or unknown"

    return nav_stat
                
def get_ship_data(mmsi, imo):
    #If imo not found, use mmsi to find ships page
    if imo==0:
        site = 'https://www.vesseltracker.com/en/vessels.html?term=' + str(mmsi)
        response = requests.get(site)
        soup = BeautifulSoup(response.content, 'html.parser')
        divs = soup.findAll("div",{"class":"row odd"})
        for links in divs:
            link = links.find('a', href=True)
            ship_link = link.get('href')
        site = "https://www.vesseltracker.com" + ship_link
        print(site)
    #If IMO exists use that
    else:
        site = "https://vesseltracker.com/en/Ships/" + str(imo) + ".html"
        #print(site)
        
    response = requests.get(site)
    soup = BeautifulSoup(response.content, 'html.parser')
    vessels = {}
    tab = soup.findAll("div",{"class":"key-value-table"})
    for t in tab:
        te = t.findAll("div",{"class":"row"})
        for t in te:
            try:
                p = t.find("div",{"class":"col-xs-5 key"})
                g = t.find("div",{"class":"col-xs-7 value"})
                vessels.update( {p.string : g.string} )
            except:
                pass
    photo = soup.find("div",{"class":"detail-image"})    
    images = photo.findAll('img')
    for image in images:
        ship_photo_url = ("https://" + image['src'])
        if ship_photo_url == "https:///assets/img/gen_img_ship.png":
            ship_photo_url = "https://www.vesseltracker.com/assets/img/gen_img_ship.png"
        else:
            pass
    flag = vessels["Flag:"]
    #Change Width and length "12.0 m" format to float "12.0"
    width = float(vessels["Width:"].split(" ")[0])
    length = float(vessels["Length:"].split(" ")[0]) 
    
    #Tähän returnin sijasta tallennus tauluun 
    return mmsi, flag, width, length, ship_photo_url

#Saves scraped ship data to DB
def save_ship_to_DB(shipData, mmsi,imo, name, ship_type, draught):
    mmsi, flag, width, length, image = get_ship_data(mmsi, imo)                            
    shipDataDocument = {
    "name": name,
    "mmsi": mmsi,
    "imo": imo,
    "shipType":ship_type,
    "draught": draught,
    "width":width,
    "length":length,
    "flag":flag,
    "image":image
    }
    shipData.insert_one(shipDataDocument)  
    print("Inserted:", name, "to DB")

#Finds the closest ship that is coming towards to Mustola
def get_closest_ship(location_data, radius, homeLat, homeLong):
    shortest_distance = radius
    closest_ship = {}
    #Tähän omana funktiona lähimmän laivan tietojen etsiminen ja palauttaa sen JSONin.
    
    for p in location_data['features']: 
        #Getting navigation status, course and coordinates
        nav_stat = p['properties']['navStat']
        course = p['properties']['cog']     
        long = p['geometry']['coordinates'][0]
        lat = p['geometry']['coordinates'][1]

        """Only ships that are coming towards and are moving, Ship status has to be something else than anchored
        Ship needs to be in the channel and not in lake Saimaa. Ship is coming towards to Mustola channel"""
        if nav_stat not in (1,5) and (lat < 61.0804652 and long > 28.2754649) and (((200 < course < 360) and lat < homeLat and long > homeLong) or ((30 < course < 180) and lat > homeLat and long < homeLong)):

            #Calculating distance       
            longitude = p['geometry']['coordinates'][0]
            latitude = p['geometry']['coordinates'][1]
            distance = calculate_distance(homeLat, homeLong, latitude, longitude)

            if distance < shortest_distance:
                shortest_distance = distance
                closest_ship = p
            #Tähän tsekki, että otetaan vain lähin laiva    
        else:
            pass   
    return closest_ship 

#Fetches ship information from API
def fetch_ships():

    #Sets api_call parameters
    home_coordinates = [61.058983,28.320951]
    radius = 50
    current_time = iso_time()

    #Tähän Try Except ja laivoja ei löydy. 

    api_call = "https://meri.digitraffic.fi/api/v1/locations/latitude/" + str(home_coordinates[0]) +"/longitude/" + str(home_coordinates[1]) + "/radius/" + str(radius) + "/from/" + current_time
    response = requests.get(api_call)
    location_data = (response.json())
    ship = get_closest_ship(location_data, radius, home_coordinates[0], home_coordinates[1])

    #Kun lähin laiva tiedossa niin valitaan sen tiedot. Jos JSON empty niin return 0
    speed = ship['properties']['sog']
    mmsi = ship['mmsi']
    heading = ship['properties']['heading']
    course = ship['properties']['cog']
    longitude = ship['geometry']['coordinates'][0]
    latitude = ship['geometry']['coordinates'][1]
    distance = calculate_distance(home_coordinates[0],home_coordinates[1],latitude,longitude)
    
    #Change nav_status type from number to name. e.g 5 = moored
    nav_stat_number = ship['properties']['navStat']
    nav_stat = get_nav_status(nav_stat_number)

    #Getting more specific shipdata from API
    vessel_details_api_call = "https://meri.digitraffic.fi/api/v1/metadata/vessels/" + str(mmsi)
    response = requests.get(vessel_details_api_call)
    details = (response.json())
    destination = details['destination']
    name = details['name']
    draught = details['draught'] / 10 #Number divided by 10 to get real draught
    imo = details['imo']
    ship_type_number = details['shipType']
    ship_type = get_ship_type (ship_type_number)

    #Open connection to mongoDB 
    client = MongoClient("mongodb+srv://dbUser:3NSPv8pakvWLUne@mustola.g1flp.mongodb.net/ships?retryWrites=true&w=majority")

    db = client.ships
    shipData = db.shipDetails
    #Checks if ship data is found in DB
    cursor = shipData.find_one( {'mmsi': mmsi })
    if cursor:
        pass
    #If ship details not in DB will fetch and save it to DB
    else:
        save_ship_to_DB(shipData, mmsi, imo, name, ship_type, draught)
    
    #Haetaan DB:stä aikaisemmin sinne raavitut tiedot
    cursor = shipData.find_one( {'mmsi': mmsi })
    flag = cursor['flag']
    width = cursor['width']
    length = cursor['length']
    image = cursor['image']

    #Palauteteaan tiedot
    return (name, mmsi, distance, destination, speed, width, length, flag, image, nav_stat, ship_type, draught, latitude, longitude)


@app.route("/", methods=["GET", "POST"])
def analysator():
    if request.method == "POST":
        
        try:
            name, mmsi, distance, destination, speed, width, length, flag, image, nav_stat, ship_type, draught, latitude, longitude = fetch_ships()
            return jsonify({'name':name, 'mmsi':mmsi, 'distance':distance, 'destination':destination, 'speed':speed, 'width':width, 'length':length, 
            'flag':flag, 'image':image, 'navStat':nav_stat, 'shipType':ship_type, 'draught':draught, 'latitude':latitude, 'longitude':longitude})
            
        except: 
             return jsonify({'name':"", 'mmsi':"", 'distance':"", 'destination':"", 'speed':"", 'width':"", 'length':"", 
            'flag':"", 'image':"", 'navStat':"", 'shipType':"", 'draught':"", 'latitude':"", 'longitude':""})
            
    try:
        name, mmsi, distance, destination, speed, width, length, flag, image, nav_stat, ship_type, draught, latitude, longitude = fetch_ships()
        return render_template("public/home.html", name=name, mmsi=mmsi, distance=distance, destination=destination, speed=speed, width=width, length=length, 
        flag=flag, image=image, navStat=nav_stat, shipType=ship_type, draught=draught, latitude=latitude, longitude=longitude)
    except:
        return render_template("public/home.html", name="", mmsi="", distance="", destination="", speed="", width="", length="", 
        flag="", image="", navStat="", shipType="", draught="", latitude="", longitude="")

@app.route("/tietoa")
def about():
    return render_template("public/about.html")
