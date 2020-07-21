## builtin imports
import os
import sys 
import h5py
import matplotlib 
matplotlib.use('Agg') 
import matplotlib.pyplot as plt
import numpy as np 
import ctypes

## abg_python imports
from abg_python.plot_utils import addColorbar
from abg_python.all_utils import append_function_docstring,append_string_docstring
from abg_python.galaxy.metadata_utils import metadata_cache

## firestudio imports
from firestudio.studios.studio import Studio

from firestudio.utils.stellar_utils import raytrace_projection,load_stellar_hsml
import firestudio.utils.stellar_utils.make_threeband_image as makethreepic


class StarStudio(Studio):
    """ `FIREstudio` class for making mock hubble images with 
        attenuation along the line of sight. 

* [`StarStudio.get_mockHubbleImage`](#starstudioget_mockhubbleimage) 
* [`StarStudio.render`](#starstudiorender) 
* [`Studio.__init__`](#studio__init__) 
* [`Studio.set_ImageParams`](#studioset_imageparams)"""

    def __repr__(self):
        return 'StarStudio instance'

####### makeOutputDirectories implementation #######
    def set_ImageParams(
        self,
        use_defaults=False,
        loud=True,
        **kwargs):
        """Changes the parameters of the image. If `use_defaults=True` then 
            default values of the parameters will be set. Leave `use_defaults=False`
            to adjust only the keywords passed. 

            Input: 

                maxden = 0.01 --  controls the saturation of the image in a non-obvious way
                dynrange = 100  --  controls the saturation of the image in a non-obvious way
                color_schem_nasa = True -- 
                loud -- 
            
            Output: 

                None

Example usage:
```python
starStudio.set_ImageParams(
    maxden=0.1,
    dynrange=10,
    figure_label='Hubble')
```"""

        default_kwargs = {
            'maxden' : 1.0e-2, ## 
            'dynrange' : 100.0, ## controls the saturation of the image in a non-obvious way
            'color_scheme_nasa' : True} ## flag to use nasa colors (vs. SDSS if false)

        for kwarg in kwargs:
            ## only set it here if it was passed
            if kwarg in default_kwargs:
                ## remove it from default_kwargs
                default_kwargs.pop(kwarg)
                value = kwargs[kwarg]
                if loud:
                    print("setting",kwarg,
                        'to user value of:',value)
                ## set it to the object
                setattr(self,kwarg,value)

        if use_defaults:
            ## set the remaining image parameters to their default values
            for default_arg in default_kwargs:
                value = default_kwargs[default_arg]
                if loud:
                    print("setting",default_arg,
                        'to default value of:',value)
                setattr(self,default_arg,value)

        ## set any other image params here
        super().set_ImageParams(use_defaults=use_defaults,**kwargs)

    append_function_docstring(set_ImageParams,Studio.set_ImageParams,prepend_string='passes `kwargs` to:\n')

    def print_ImageParams(self):
        """ Prints current image setup to console.

            Input:

                None

            Output:

                None"""

        default_kwargs = {
            'maxden' : 1.0e-2, ## 
            'dynrange' : 100.0, ## controls the saturation of the image in a non-obvious way
            'color_scheme_nasa' : True} ## flag to use nasa colors (vs. SDSS if false)

        ## print the current value, not the default value
        for arg in default_kwargs:
            print(arg,'=',getattr(self,arg))

        ## call the super class' print image params
        super().print_ImageParams()

####### projectImage implementation #######
    def get_mockHubbleImage(
        self,
        use_metadata=True,
        save_meta=True,
        assert_cached=False,
        loud=True,
        **kwargs, 
        ):
        """Projects starlight and approximates attenuatation along line of sight
            into SDSS u, g, and r bands. 

            Input:

                use_metadata = True -- flag to search cache for result
                save_meta = True -- flag to cache the result
                assert_cached = False -- flag to require a cache hit
                loud = True -- whether cache hits/misses should be announced
                    to the console.

            Output:

                gas_out -- total mass along LOS in pixel, in unknown units
                out_u -- total attenuated luminosity along LOS in pixel
                    in u band, in unknown units
                out_g -- total attenuated luminosity along LOS in pixel
                    in g band, in unknown units
                out_r -- total attenuated luminosity along LOS in pixel
                    in r band, in unknown units"""

        @metadata_cache(
            self.this_setup_id,  ## hdf5 file group name
            ['starMassesMap',
                'attenUMap',
                'attenGMap',
                'attenRMap'],
            use_metadata=use_metadata,
            save_meta=save_meta,
            assert_cached=assert_cached,
            loud=loud,
            force_from_file=True)  ## read from cache file, not attribute of object
        def compute_mockHubbleImage(self):

            ## cull the particles outside the frame and cast to float32
            star_ind_box = self.cullFrameIndices(self.star_snapdict['Coordinates'])
            print(np.sum(star_ind_box),'many star particles in volume')

            ## unpack the star information
            ## dont' filter star positions just yet
            star_pos = self.star_snapdict['Coordinates']

            ## try opening the stellar smoothing lengths, if we fail
            ##  let's calculate them and save them to the projection 
            ##  file

            if "SmoothingLength" not in self.star_snapdict:
                Hsml = self.get_HSML('star')
            else:
                Hsml = self.star_snapdict['SmoothingLength'] ## kpc
            ## attempt to pass these indices along
            h_star = Hsml[star_ind_box].astype(np.float32)

            ## and now filter the positions
            star_pos = star_pos[star_ind_box].astype(np.float32)

            ## rotate by euler angles if necessary
            star_pos = self.rotateEuler(self.theta,self.phi,self.psi,star_pos)

            mstar = self.star_snapdict['Masses'][star_ind_box].astype(np.float32)
            ages = self.star_snapdict['AgeGyr'][star_ind_box].astype(np.float32)
            metals = self.star_snapdict['Metallicity'][:,0][star_ind_box].astype(np.float32)

            ## cull the particles outside the frame and cast to float32
            gas_ind_box = self.cullFrameIndices(self.gas_snapdict['Coordinates'])
            print(np.sum(gas_ind_box),'many gas particles in volume')

            ## unpack the gas information
            gas_pos = self.gas_snapdict['Coordinates'][gas_ind_box]

            ## rotate by euler angles if necessary
            gas_pos = self.rotateEuler(self.theta,self.phi,self.psi,gas_pos).astype(np.float32)

            mgas = self.gas_snapdict['Masses'][gas_ind_box].astype(np.float32)
            gas_metals = self.gas_snapdict['Metallicity'][:,0][gas_ind_box].astype(np.float32)

            if "SmoothingLength" not in self.gas_snapdict:
                h_gas = self.get_HSML('gas')
            else:
                h_gas = self.gas_snapdict['SmoothingLength'][gas_ind_box].astype(np.float32)

            ## do the actual raytracing
            gas_out,out_u,out_g,out_r = raytrace_ugr_attenuation(
                star_pos[:,0],star_pos[:,1],star_pos[:,2],
                mstar,ages,metals,
                h_star,
                gas_pos[:,0],gas_pos[:,1],gas_pos[:,2],
                mgas,gas_metals,h_gas,
                pixels=self.pixels)

            return gas_out,out_u,out_g,out_r
        return compute_mockHubbleImage(self,**kwargs)

####### produceImage implementation #######
    def render(
        self,
        ax=None,
        **kwargs):
        """Plots a mock hubble image, along with any annotations/scale bars,
            using the stored image parameters.

            Input: 

                ax = None -- axis to plot image to, if None will create a new figure

            Output:

                ax -- the axis the image was plotted to
                final_image -- 2x2x3 RGB pixel array

Example usage:
```python
starStudio.render(plt.gca())
```"""

        if ax is None:
            fig,ax = plt.figure(),plt.gca()
        else:
            fig = ax.get_figure()

        ## remap the C output to RGB space
        final_image = self.__produceImage(**kwargs)

        ## plot that RGB image and overlay scale bars/text
        self.plotImage(ax,final_image)

        ## save the image
        if self.savefig is not None:
            self.saveFigure(ax,self.savefig)

        return ax,final_image

    def __produceImage(
        self,
        **kwargs):

        gas_out,out_u,out_g,out_r = self.get_mockHubbleImage(**kwargs)

        ## open the hdf5 file and load the maps
        image24, massmap = makethreepic.make_threeband_image_process_bandmaps(
            out_r,out_g,out_u,
            maxden=self.maxden,
            dynrange=self.dynrange,
            pixels=self.pixels,
            color_scheme_nasa=self.color_scheme_nasa,
            color_scheme_sdss=not self.color_scheme_nasa)

        ## for some reason it's rotated 90 degrees...? kind of like transposed but different
        ##  need to take the rows of the output image and make them the columns, iteratively,
        ##  for now... 
        #image24=np.rot90(image24,k=1,axes=(0,1))
        final_image = np.transpose(image24,axes=(1,0,2))
        self.final_image = final_image

        return final_image

append_function_docstring(StarStudio,StarStudio.set_ImageParams)
append_function_docstring(StarStudio,StarStudio.get_mockHubbleImage)
append_function_docstring(StarStudio,StarStudio.render)
append_function_docstring(StarStudio,Studio)

##### Image projection stuff
## Stellar light attenuation projection
def raytrace_ugr_attenuation(
    x,y,z,
    mstar,ages,metals,
    h_star, 
    gx,gy,gz,
    mgas, gas_metals,
    h_gas,
    pixels = 1200,
    xlim = None, ylim = None, zlim = None
    ):

    ## setup boundaries to cut-out gas particles that lay outside
    ## range
    if xlim is None:
        xlim = [np.min(x),np.max(x)]
    if ylim is None:
        ylim = [np.min(y),np.max(y)]
    if zlim is None:
        zlim = [np.min(z),np.max(z)]

#   band=BAND_ID; # default=bolometric
#   j = [  0,  6,  7,  8,  9, 10, 11, 12, 13,  1,   2,   3,   4,   5] # ordering I'm used to
#   i = [  0,  1,  2,  3,  4,  5,  6,  7,  8,  9,  10,  11,  12,  13] # ordering of this
#   band_standardordering = band
#   band = j[band]
#   if (band > 13): 
#       print 'BAND_ID must be < 13'; 
#       return 0;
#   
#   b=['Bolometric', \
#   'Sloan u','Sloan g','Sloan r','Sloan i','Sloan z', \
#   'Johnsons U','Johnsons B', 'Johnsons V','Johnsons R','Johnsons I', \
#   'Cousins J','Cousins H','Cousins K']
    ## pick color bands by their IDs, see above
    BAND_IDS=[9,10,11]
    #gas_out,out_u,out_g,out_r = stellar_raytrace(
    return raytrace_projection.stellar_raytrace(
        BAND_IDS,
        x,y,z,
        mstar,ages,metals,
        h_star,
        gx,gy,gz,
        mgas, gas_metals,
        h_gas,
        pixels=pixels,
        xlim=xlim,ylim=ylim,zlim=zlim,
        ADD_BASE_METALLICITY=0.001*0.02,ADD_BASE_AGE=0.0003,
        IMF_SALPETER=0,IMF_CHABRIER=1
    )

__doc__  = ''
__doc__ = append_string_docstring(__doc__,StarStudio)
