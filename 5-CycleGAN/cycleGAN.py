import tensorflow as tf
from tensorflow.keras import layers, models
from tensorflow.keras.utils import plot_model
import numpy as np
import os, sys, pickle
import matplotlib.pyplot as plt



class CycleGAN():
    def __init__(self, generator_ab, generator_ba, discriminator_a, discriminator_b, input_shape, patch_shape):
       
        # set init vars
        self.name = 'cycleGAN'
        self.gene_ab = generator_ab
        self.gene_ba = generator_ba
        self.disc_a = discriminator_a
        self.disc_b = discriminator_b
        self.input_shape = input_shape
        self.patch_shape = patch_shape
    
    
    def compile( self
               , optimizer 
               , lambda_valid = 1 
               , lambda_cycle = 10
               , lambda_ident = 9 ):
        
        binary = tf.keras.losses.BinaryCrossentropy(from_logits=True)

        self.disc_a.compile(loss=binary, optimizer=optimizer, metrics=['accuracy'])
        self.disc_b.compile(loss=binary, optimizer=optimizer, metrics=['accuracy'])
        
        self.disc_a.trainable=False
        self.disc_b.trainable=False

        img_a = layers.Input(shape = self.input_shape, name='input_a')
        img_b = layers.Input(shape = self.input_shape, name='input_b')
        
        fake_a = self.gene_ba(img_b)
        fake_b = self.gene_ab(img_a)
        
        valid_a = self.disc_a(fake_a)
        valid_b = self.disc_b(fake_b)
        
        cycle_a = self.gene_ba(fake_b)
        cycle_b = self.gene_ab(fake_a)
        
        ident_a = self.gene_ba(img_a)
        ident_b = self.gene_ab(img_b)
        
        self.cyclegan = models.Model(name='CycleGAN',
                                inputs=[img_a, img_b], 
                                outputs=[valid_a, valid_b, 
                                        cycle_a, cycle_b,
                                        ident_a, ident_b
                                        ])
        
        self.cyclegan.compile(loss = [binary, binary, 'mae', 'mae', 'mae', 'mae'],
                              loss_weights=[lambda_valid, lambda_valid, 
                                            lambda_cycle, lambda_cycle, 
                                            lambda_ident, lambda_ident],
                              optimizer=optimizer) 
        
        self.disc_a.trainable=True
        self.disc_b.trainable=True


    def _make_datasets(self, x_data, batch_size):
        dataset = tf.data.Dataset.from_tensor_slices(x_data).shuffle(1)
        dataset = dataset.batch(batch_size, drop_remainder=True).prefetch(1)
        return dataset
    
    def _make_constant(self, batch_size):
        y1 = np.ones((batch_size, ) + self.patch_shape)
        y0 = np.zeros((batch_size,) + self.patch_shape)
        return y0, y1
        
    def fit(self, train_a, train_b, epochs=1, batch_size=8, img_iter=5, save_path=None):
        
        # set data
        dataset_a = self._make_datasets(train_a, batch_size)
        dataset_b = self._make_datasets(train_b, batch_size)
        # set constant 
        y0, y1 = self._make_constant(batch_size)
        
        # train
        self.plot_sample_images(train_a, self.gene_ab)
        self.plot_sample_images(train_b, self.gene_ba)
        history = {'d_loss':[], 'g_loss':[], 'valid_loss':[], 'cycle_loss':[], 'ident_loss':[]}
        for epoch in range(epochs):
            
            disc_loss, gene_loss, valid_loss, cycle_loss, ident_loss  = 0, 0, 0, 0, 0
            for imgs_a, imgs_b in zip (dataset_a, dataset_b):
            
                fake_b = self.gene_ab.predict(imgs_a)
                fake_a = self.gene_ba.predict(imgs_b)
                
                self.disc_a.trainable = True
                self.disc_b.trainable = True
                
                da_loss_real = self.disc_a.train_on_batch(imgs_a, y1)
                da_loss_fake = self.disc_a.train_on_batch(fake_a, y0)
                da_loss = 0.5*np.add(da_loss_real, da_loss_fake)

                db_loss_real = self.disc_b.train_on_batch(imgs_b, y1)
                db_loss_fake = self.disc_b.train_on_batch(fake_b, y0)
                db_loss = 0.5*np.add(db_loss_real, db_loss_fake)
                d_loss = 0.5*np.add(da_loss, db_loss)
                
                self.disc_a.trainable = False
                self.disc_b.trainable = False
                g_loss = self.cyclegan.train_on_batch([imgs_a, imgs_b],
                                                     [y1, y1, imgs_a, imgs_b, imgs_a, imgs_b]) 
                disc_loss = disc_loss + d_loss[0]
                valid_loss=valid_loss + g_loss[0] + g_loss[1]
                cycle_loss=cycle_loss + g_loss[2] + g_loss[3]
                ident_loss=ident_loss + g_loss[4] + g_loss[5]
                gene_loss = gene_loss + valid_loss + cycle_loss + ident_loss 
            
            print(d_loss, g_loss)
            history['d_loss'].append(disc_loss)
            history['g_loss'].append(gene_loss)
            history['valid_loss'].append(valid_loss)
            history['cycle_loss'].append(cycle_loss)
            history['ident_loss'].append(ident_loss)
            print("* epoch {}/{}: ".format(epoch, epochs), 'd_loss: %f, g_loss: %f, valid_loss: %f, cycle_loss: %f, ident_loss: %f'%(disc_loss, gene_loss, valid_loss, cycle_loss, ident_loss))
            
            if epoch%img_iter==0:
                if save_path: 
                    self.plot_sample_images(train_a, self.gene_ab, save_name='%s/sample_ab_%i'%(save_path, epoch))
                    self.plot_sample_images(train_b, self.gene_ba, save_name='%s/sample_ba_%i'%(save_path, epoch))
                else:     
                    self.plot_sample_images(train_a, self.gene_ab)
                    self.plot_sample_images(train_b, self.gene_ba)
        
        return history

    def plot_sample_images(self, imgs, gene, save_name=None):
        r, c = 2, 5
        gen_imgs = gene.predict(imgs[:r*c])

        #Rescale images 0 - 1
        gen_imgs = 0.5 * (gen_imgs + 1)
        gen_imgs = np.clip(gen_imgs, 0, 1)
        imgs = 0.5 * (imgs + 1)
        imgs = np.clip(imgs, 0, 1)
        
        plt.figure(figsize=(c*5,r*5))
        for i, img in enumerate(imgs[:c]):
            plt.subplot(r, c, i+1)
            plt.imshow(np.squeeze(img), cmap='gray_r' )
            plt.xticks([])
            plt.yticks([])
        for i, img in enumerate(gen_imgs[:c]):
            plt.subplot(r, c, c+i+1)
            plt.imshow(np.squeeze(img), cmap='gray_r' )
            plt.xticks([])
            plt.yticks([])

        if save_name:
            plt.savefig(save_name)
        else: plt.show()
        plt.close()
    
    def plot_model(self, save_path='.'):
        tf.keras.utils.plot_model( 
                    self.gene_ab
                  , to_file='%s/gene.png'%save_path
                  , show_shapes = True)
        tf.keras.utils.plot_model( 
                    self.disc_a
                  , to_file='%s/disc.png'%save_path
                  , show_shapes = True)
    def save_model(self, save_path='.'):
        self.cyclegan.save('%s/cyclegan.h5'%save_path)
        self.gene_ab.save('%s/gene_ab.h5'%save_path)
        self.gene_ba.save('%s/gene_ba.h5'%save_path)
        self.disc_a.save('%s/disc_a.h5'%save_path)
        self.disc_b.save('%s/disc_b.h5'%save_path)
