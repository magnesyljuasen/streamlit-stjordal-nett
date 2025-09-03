import streamlit as st
import pandas as pd 
import folium
from folium.plugins import FastMarkerCluster
from streamlit_folium import st_folium
import geopandas as gpd
from branca.colormap import LinearColormap
import plotly.graph_objs as go
import numpy as np
import streamlit_authenticator as stauth
import yaml

def streamlit_login():
    with open('src/login/config.yaml') as file:
        config = yaml.load(file, Loader=stauth.SafeLoader)
        authenticator = stauth.Authenticate(config['credentials'],config['cookie']['name'],config['cookie']['key'],config['cookie']['expiry_days'])
        name, authentication_status, username = authenticator.login(fields = {'Form name' : "Næringslivets arealplan Stjørdal - Data fra Tensio", 'Username' : 'Brukernavn', 'Passowrd' : 'Passord', 'Login' : 'Logg inn'})
        #name, authentication_status, username = authenticator.login('Innlogging', 'main')
    return name, authentication_status, username, authenticator

def streamlit_login_page(name, authentication_status, username, authenticator):
    if authentication_status == False: # ugyldig passord
        st.error('Ugyldig brukernavn/passord')
        st.stop()
    elif authentication_status == None: # ingen input
        #st.image(Image.open('src/data/img/kolbotn_sesongvarmelager.jpg'))
        st.stop()
    elif authentication_status: # app start
        with st.sidebar:
            #st.image(Image.open('src/data/img/av_logo.png')) # logo
            #st.write(f"*Du er logget inn som {name}.*")
            authenticator.logout('Logg ut')

def merge_dfs(dfs):
    merged_df = dfs[0]
    for df in dfs[1:]:
        merged_df = pd.merge(merged_df, df, how='outer', on='Dato_kort')
    return merged_df

@st.cache_resource(show_spinner=False)
def import_dfs():
    df_hourly_data = pd.read_excel("src/AMS Stjørdal.xlsx", sheet_name="Timedata")
    df_grid_stations = pd.read_excel("src/AMS Stjørdal.xlsx", sheet_name="Nettstasjon")
    df_buildings = pd.read_excel("src/AMS Stjørdal.xlsx", sheet_name="Målepunkt")
    df_ns = pd.read_excel("src/AMS Stjørdal.xlsx", sheet_name="NS")
    df_buildings = pd.merge(df_buildings, df_ns, on='Driftsmerking', how='inner')
    return df_hourly_data, df_grid_stations, df_buildings

### Streamlit settings
st.set_page_config(page_title="Næringslivets arealplan Stjørdal - Data fra Tensio", page_icon="📊", layout="wide", initial_sidebar_state="expanded")


### Login
name, authentication_status, username, authenticator = streamlit_login()
streamlit_login_page(name, authentication_status, username, authenticator)


### Sidebar settings
with st.sidebar:
    st.image("src/AV-logo.png", use_column_width=True)
    st.write("*Næringslivets arealplan Stjørdal - Data fra Tensio*")
with open("main.css") as f:
    st.markdown("<style>{}</style>".format(f.read()), unsafe_allow_html=True)

with st.spinner("Laster inn..."):
    ### Import dataframes
    df_hourly_data, df_grid_stations, df_buildings = import_dfs()

    ### Filter grid stations
    idx_drop_list = []
    unique_grid_stations = list(df_hourly_data.columns)
    for idx, row in df_grid_stations.iterrows():
        grid_station_name = row["Nettstasjonsnavn"]
        if grid_station_name in unique_grid_stations:
            pass
        else:
            idx_drop_list.append(idx)
    df_grid_stations.drop(idx_drop_list, inplace=True)
    df_grid_stations.reset_index(drop=True, inplace=True)


    ### Remove buildpoints outside map
    idx_drop_list = []
    unique_markers = list(df_grid_stations["Driftsmerking"].unique())
    for idx, row in df_buildings.iterrows():
        marker = str(int(row["Driftsmerking"]))
        if marker in unique_markers:
            pass
        else:
            idx_drop_list.append(idx)
    df_buildings.drop(idx_drop_list, inplace=True)
    df_buildings.reset_index(drop=True, inplace=True)


    ### Mapping 
    m = folium.Map(
        location=[df_buildings['Geografisk nord (grader)'].mean(), df_buildings['Geografisk øst (grader)'].mean()], 
        zoom_start=15,
        max_zoom=22,
        control_scale=True,
        prefer_canvas=True)
    folium.TileLayer("CartoDB positron", name="Bakgrunnskart").add_to(m)
        
    gdf = gpd.GeoDataFrame(df_buildings, geometry=gpd.points_from_xy(df_buildings['Geografisk øst (grader)'], df_buildings['Geografisk nord (grader)']))
    colormap = LinearColormap(['green', 'yellow'], vmin=0, vmax=1)

    for idx, row in gdf.iterrows():
        marker = str(row['Driftsmerking'])
        percentage = row['%-belastning per i dag']
        color = colormap(percentage)
        if row['Installert trafoytelse'] == 0:
            color = "gray"
        folium.CircleMarker(
            location=[row['geometry'].y, row['geometry'].x],
            radius=10,
            color='transparent',
            fill=True,
            fill_color=color,
            fill_opacity=0.7,
            tooltip=f"Maks belastning: {int(row['Maks belastning [kWh/h]'])} kW<br>Installert trafoytelse {row['Installert trafoytelse']} kW"
            ).add_to(m)

    st_data = st_folium(m, height=400, use_container_width=True, returned_objects=["last_object_clicked"])


    ### Returned data from map 
    returned_data = st_data["last_object_clicked"]
    if returned_data == None:
        st.info("Klikk på ett målepunkt på kartet for å vise data", icon="ℹ️")
        st.stop()
    else:
        north = returned_data["lat"]
        east = returned_data["lng"]
        bbox = 0.001
        min_lat, max_lat = north - bbox, north + bbox
        min_lon, max_lon = east - bbox, east + bbox
        df_buildings_filtered = df_buildings[(df_buildings['Geografisk nord (grader)'] >= min_lat) & (df_buildings['Geografisk nord (grader)'] <= max_lat) & (df_buildings['Geografisk øst (grader)'] >= min_lon) & (df_buildings['Geografisk øst (grader)'] <= max_lon)]
        grid_station_id = list(df_buildings_filtered["Driftsmerking"])[0]

        df_grid_stations_filtered = df_grid_stations[df_grid_stations['Driftsmerking'] == str(grid_station_id)]
        grid_station_capacity = int(df_grid_stations_filtered["Installert trafoytelse"])
        grid_station_name = df_grid_stations_filtered["Nettstasjonsnavn"].iloc[0]
        df_selected_data = df_hourly_data[["Dato", "TEMPERATUR", grid_station_name]]


    ### Hourly data processing
    df_selected_data['Dato'] = pd.to_datetime(df_selected_data['Dato'])
    df_selected_data.set_index('Dato', inplace=True)
    df_selected_data['Dato_kort'] = df_selected_data.index.strftime('%m.%d.%H')

    df_temperature_data = df_selected_data.copy()
    df_selected_data = df_selected_data.drop(columns=['TEMPERATUR'])
    df_temperature_data = df_temperature_data.drop(columns=[grid_station_name])

    years_data = []
    for year, data in df_selected_data.groupby(df_selected_data.index.year):
        data = data.rename(columns={grid_station_name: year})
        years_data.append(data)

    temperature_years_data = []
    for year, data in df_temperature_data.groupby(df_selected_data.index.year):
        data = data.rename(columns={f"TEMPERATUR": year})
        temperature_years_data.append(data)

    df_merged = merge_dfs(years_data)
    df_merged.set_index('Dato_kort', inplace=True)
    df_merged = df_merged.fillna(0)

    df_temperature_merged = merge_dfs(temperature_years_data)
    df_temperature_merged.set_index('Dato_kort', inplace=True)
    df_temperature_merged = df_temperature_merged.fillna(0)


    ### Set station name
    #st.write(f"Du har valgt: **{grid_station_name}**")


    ### Plot using plotly
    COLOR_LIST = ["rgba(29,60,52,0.8)", "rgba(183,220,143,0.8)", "rgba(72,162,63,0.8)", "rgba(0,0,0,0.8)"]
    WEAK_COLOR_LIST = ["rgba(29,60,52,1.0)", "rgba(183,220,143,1)", "rgba(72,162,63,1)", "rgba(0,0,0,1)"]
    with st.sidebar:
        st.write("")
        st.markdown("---")
        st.write("")
        st.header("**Innstillinger for graf**")
        years = st.multiselect("**Hvilke(t) år vil du se på?**", options=["2021", "2022", "2023"], default="2022")
        st.write("")
        temperature_curve = st.checkbox("**Med utetemperatur?**", value=True)
        st.write("")
        effect_duration_curve = st.checkbox("**Som varighetskurve?**", value=False)
    fig = go.Figure()
    for index, column in enumerate(df_merged.columns[1:]):
        year = f"202{index+1}"
        if year in list(years):
            show = True
        else:
            show = 'legendonly'
        if effect_duration_curve:
            x_axis = np.arange(0, len(df_merged[column]))
            fig.add_trace(go.Scatter(x=x_axis, y=np.sort(df_merged[column])[::-1], mode='lines', visible=show, name=column, line=dict(width=1.5, color=COLOR_LIST[index])))
        else:
            fig.add_trace(go.Bar(x=df_merged.index, y=df_merged[column], name=column, visible=show, marker=dict(color=COLOR_LIST[index])))
            if temperature_curve:
                fig.add_trace(go.Scatter(x=df_temperature_merged.index, y=df_temperature_merged[column], mode='lines', visible=show ,name=f"Utetemperatur {column}", yaxis='y2', line=dict(width=0.5, dash='dot', color=WEAK_COLOR_LIST[index])))

    if grid_station_capacity > 0:
        max_capacity = grid_station_capacity*1.1
        if effect_duration_curve:
            fig.add_shape(type="line", x0=min(x_axis), y0=grid_station_capacity, x1=max(x_axis), y1=grid_station_capacity, line=dict(color="black", width=2, dash="dash"))
        else:
            fig.add_shape(type="line", x0=min(df_merged.index), y0=grid_station_capacity, x1=max(df_merged.index), y1=grid_station_capacity, line=dict(color="black", width=2, dash="dash"))
        fig.add_trace(go.Scatter(x=[None], y=[None], mode='lines', name=f"Kapasitet {grid_station_capacity} kW", line=dict(color="black", width=2, dash="dash")))
    else:
        max_capacity = None

    fig.update_layout(
        legend=dict(
            orientation="h",
            yanchor="top",
            y=1.1,
            xanchor="center",
            x=0.5
        ),
        yaxis_range=[0, max_capacity],
        xaxis_title=None,
        margin=dict(l=50, r=50, t=50, b=50),
        yaxis_title='Timesmidlet effekt (kWh/h)',
        yaxis2=dict(title="Temperatur (°C)", overlaying="y", side="right"),
        )

    st.plotly_chart(fig, height=400, use_container_width=True, config = {'displayModeBar': False, 'staticPlot': False})


    ### Metrics
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric(label=f"Kapasitet", value=f"{grid_station_capacity:,} kW".replace(",", " "))
    for index, column in enumerate(df_merged.columns[1:]):
        max_effect = int(df_merged[column].max())
        sum_effect = int(df_merged[column].sum())
        if grid_station_capacity > 0:
            percentage_load = int((max_effect/grid_station_capacity)*100)
        else:
            percentage_load = "-"
        if index == 0:
            col = c2
        if index == 1:
            col = c3
        if index == 2:
            col = c4
        with col:
            st.metric(label=f"{column}", value=f"{max_effect:,} kW ({percentage_load} %)".replace(",", " "), delta = f"{sum_effect:,} kWh".replace(",", " "), delta_color="off")