import * as FileSystem from 'expo-file-system';
import * as Sharing from 'expo-sharing';
import { Platform } from 'react-native';

interface Vote {
  personId: string;
  personName: string;
  category: string;
  vote: number;
  timestamp: string;
}

/**
 * Export des votes en format CSV
 */
export async function exportToCSV(votes: Vote[]): Promise<void> {
  try {
    // Créer le contenu CSV
    const headers = 'Date,Personnalité,Catégorie,Vote\n';
    const rows = votes.map(v => {
      const date = new Date(v.timestamp).toLocaleString('fr-FR');
      const voteType = v.vote === 1 ? 'Like' : 'Dislike';
      return `"${date}","${v.personName}","${v.category}","${voteType}"`;
    }).join('\n');
    
    const csvContent = headers + rows;
    
    // Sauvegarder le fichier
    const fileName = `votes_popular_${Date.now()}.csv`;
    const fileUri = `${FileSystem.documentDirectory}${fileName}`;
    
    await FileSystem.writeAsStringAsync(fileUri, csvContent, {
      encoding: FileSystem.EncodingType.UTF8,
    });
    
    // Partager le fichier
    const canShare = await Sharing.isAvailableAsync();
    if (canShare) {
      await Sharing.shareAsync(fileUri, {
        mimeType: 'text/csv',
        dialogTitle: 'Exporter vos votes',
      });
    } else {
      throw new Error('Le partage n\'est pas disponible sur cet appareil');
    }
  } catch (error) {
    console.error('Export CSV error:', error);
    throw error;
  }
}

/**
 * Export des votes en format JSON
 */
export async function exportToJSON(votes: Vote[]): Promise<void> {
  try {
    // Créer le contenu JSON
    const jsonContent = JSON.stringify({
      exported_at: new Date().toISOString(),
      total_votes: votes.length,
      votes: votes.map(v => ({
        ...v,
        date: new Date(v.timestamp).toISOString(),
        vote_type: v.vote === 1 ? 'like' : 'dislike',
      })),
    }, null, 2);
    
    // Sauvegarder le fichier
    const fileName = `votes_popular_${Date.now()}.json`;
    const fileUri = `${FileSystem.documentDirectory}${fileName}`;
    
    await FileSystem.writeAsStringAsync(fileUri, jsonContent, {
      encoding: FileSystem.EncodingType.UTF8,
    });
    
    // Partager le fichier
    const canShare = await Sharing.isAvailableAsync();
    if (canShare) {
      await Sharing.shareAsync(fileUri, {
        mimeType: 'application/json',
        dialogTitle: 'Exporter vos votes',
      });
    } else {
      throw new Error('Le partage n\'est pas disponible sur cet appareil');
    }
  } catch (error) {
    console.error('Export JSON error:', error);
    throw error;
  }
}
