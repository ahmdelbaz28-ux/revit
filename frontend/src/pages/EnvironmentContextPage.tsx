import React, { useState } from "react";
import { useTranslation } from "react-i18next";
import { Cloud, MapPin, AlertTriangle, Droplets } from "lucide-react";

export const EnvironmentContextPage: React.FC = () => {
  const { t } = useTranslation();
  const [location, setLocation] = useState("New York, USA");
  const [latitude, setLatitude] = useState(40.7128);
  const [longitude, setLongitude] = useState(-74.006);

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-3xl font-bold text-slate-100 flex items-center gap-2">
          <Cloud className="h-8 w-8 text-blue-500" />
          Environment & Context
        </h1>
        <p className="text-slate-400 mt-2">
          Weather, geocoding, air quality, and environmental data for fire safety design
        </p>
      </div>

      {/* Tabs */}
      <div className="flex flex-wrap gap-2 border-b border-slate-700">
        <button className="px-4 py-2 border-b-2 border-blue-500 text-blue-400 font-medium">
          Weather & Geocoding
        </button>
        <button className="px-4 py-2 border-b-2 border-transparent text-slate-400 hover:text-slate-300">
          Air Quality
        </button>
        <button className="px-4 py-2 border-b-2 border-transparent text-slate-400 hover:text-slate-300">
          HazMat Database
        </button>
        <button className="px-4 py-2 border-b-2 border-transparent text-slate-400 hover:text-slate-300">
          Severe Weather
        </button>
      </div>

      {/* Content */}
      <div className="bg-slate-800/50 border border-slate-700 rounded-lg p-6 space-y-6">
        {/* Location Input */}
        <div>
          <label className="block text-sm font-medium text-slate-300 mb-2">
            Location Search
          </label>
          <div className="flex gap-2">
            <input
              type="text"
              value={location}
              onChange={(e) => setLocation(e.target.value)}
              className="flex-1 px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-slate-100 placeholder-slate-500 focus:border-blue-500 focus:outline-none"
              placeholder="Enter address or location..."
            />
            <button className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg font-medium transition-colors">
              Search
            </button>
          </div>
        </div>

        {/* Coordinates */}
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="block text-sm font-medium text-slate-300 mb-2">
              Latitude
            </label>
            <input
              type="number"
              value={latitude}
              onChange={(e) => setLatitude(Number(e.target.value))}
              className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-slate-100"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-slate-300 mb-2">
              Longitude
            </label>
            <input
              type="number"
              value={longitude}
              onChange={(e) => setLongitude(Number(e.target.value))}
              className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-slate-100"
            />
          </div>
        </div>

        {/* Weather Data - Placeholder */}
        <div className="border-t border-slate-700 pt-6">
          <h3 className="text-lg font-semibold text-slate-100 mb-4 flex items-center gap-2">
            <Cloud className="h-5 w-5 text-blue-400" />
            Current Weather
          </h3>
          <div className="grid grid-cols-4 gap-4">
            <div className="bg-slate-700/50 border border-slate-600 rounded-lg p-3">
              <div className="text-sm text-slate-400">Temperature</div>
              <div className="text-2xl font-bold text-slate-100 mt-2">Loading...</div>
            </div>
            <div className="bg-slate-700/50 border border-slate-600 rounded-lg p-3">
              <div className="text-sm text-slate-400">Humidity</div>
              <div className="text-2xl font-bold text-slate-100 mt-2">Loading...</div>
            </div>
            <div className="bg-slate-700/50 border border-slate-600 rounded-lg p-3">
              <div className="text-sm text-slate-400">Wind Speed</div>
              <div className="text-2xl font-bold text-slate-100 mt-2">Loading...</div>
            </div>
            <div className="bg-slate-700/50 border border-slate-600 rounded-lg p-3">
              <div className="text-sm text-slate-400">Pressure</div>
              <div className="text-2xl font-bold text-slate-100 mt-2">Loading...</div>
            </div>
          </div>
        </div>

        {/* Air Quality - Placeholder */}
        <div className="border-t border-slate-700 pt-6">
          <h3 className="text-lg font-semibold text-slate-100 mb-4 flex items-center gap-2">
            <Droplets className="h-5 w-5 text-green-400" />
            Air Quality Index
          </h3>
          <div className="bg-slate-700/50 border border-slate-600 rounded-lg p-4">
            <div className="text-sm text-slate-400 mb-2">AQI Status</div>
            <div className="text-3xl font-bold text-slate-100">Fetching data...</div>
            <p className="text-xs text-slate-400 mt-2">
              Data will be retrieved from OpenWeather API
            </p>
          </div>
        </div>
      </div>

      {/* Info Box */}
      <div className="bg-blue-500/10 border border-blue-500/30 rounded-lg p-4">
        <p className="text-sm text-blue-300 flex items-start gap-2">
          <AlertTriangle className="h-5 w-5 mt-0.5 shrink-0" />
          <span>
            Environmental data is used to provide context for fire alarm system design,
            including weather effects on detector spacing and performance.
          </span>
        </p>
      </div>
    </div>
  );
};

export default EnvironmentContextPage;
