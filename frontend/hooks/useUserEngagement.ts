import { useState, useEffect, useCallback } from 'react';
import AsyncStorage from '@react-native-async-storage/async-storage';

const VOTES_KEY = "popular_my_votes";
const STREAK_KEY = "popular_streak_data";

export interface Badge {
  id: string;
  name: string;
  description: string;
  icon: string;
  threshold: number;
  unlocked: boolean;
}

export interface StreakData {
  currentStreak: number;
  longestStreak: number;
  lastVoteDate: string;
}

export interface CategoryStats {
  category: string;
  count: number;
  percentage: number;
}

export interface VoteStats {
  totalLikes: number;
  totalDislikes: number;
  categoriesBreakdown: CategoryStats[];
  favoriteCategory: string;
  mostVotedPerson: { name: string; count: number };
}

const BADGES: Badge[] = [
  { id: 'beginner', name: 'Débutant', description: 'Votez 10 fois', icon: 'star-outline', threshold: 10, unlocked: false },
  { id: 'active', name: 'Actif', description: 'Votez 50 fois', icon: 'star-half-outline', threshold: 50, unlocked: false },
  { id: 'expert', name: 'Expert', description: 'Votez 100 fois', icon: 'star', threshold: 100, unlocked: false },
  { id: 'legend', name: 'Légende', description: 'Votez 250 fois', icon: 'trophy-outline', threshold: 250, unlocked: false },
  { id: 'master', name: 'Maître', description: 'Votez 500 fois', icon: 'trophy', threshold: 500, unlocked: false },
];

export function useUserEngagement() {
  const [badges, setBadges] = useState<Badge[]>(BADGES);
  const [streakData, setStreakData] = useState<StreakData>({
    currentStreak: 0,
    longestStreak: 0,
    lastVoteDate: '',
  });
  const [totalVotes, setTotalVotes] = useState(0);
  const [voteStats, setVoteStats] = useState<VoteStats>({
    totalLikes: 0,
    totalDislikes: 0,
    categoriesBreakdown: [],
    favoriteCategory: '',
    mostVotedPerson: { name: '', count: 0 },
  });

  const loadEngagementData = useCallback(async () => {
    try {
      // Load votes
      const storedVotes = await AsyncStorage.getItem(VOTES_KEY);
      const votes = storedVotes ? JSON.parse(storedVotes) : [];
      setTotalVotes(votes.length);

      // Update badges based on vote count
      const updatedBadges = BADGES.map(badge => ({
        ...badge,
        unlocked: votes.length >= badge.threshold,
      }));
      setBadges(updatedBadges);

      // Load and update streak data
      const storedStreak = await AsyncStorage.getItem(STREAK_KEY);
      const streak = storedStreak ? JSON.parse(storedStreak) : { currentStreak: 0, longestStreak: 0, lastVoteDate: '' };
      
      // Calculate streak based on votes
      if (votes.length > 0) {
        const sortedVotes = votes.sort((a: any, b: any) => 
          new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime()
        );
        
        const uniqueDays = new Set<string>();
        sortedVotes.forEach((vote: any) => {
          const date = new Date(vote.timestamp);
          const dateStr = date.toISOString().split('T')[0];
          uniqueDays.add(dateStr);
        });

        const daysArray = Array.from(uniqueDays).sort().reverse();
        let currentStreak = 0;
        let longestStreak = 0;
        let tempStreak = 1;
        
        const today = new Date();
        const todayStr = today.toISOString().split('T')[0];
        const yesterday = new Date(today);
        yesterday.setDate(yesterday.getDate() - 1);
        const yesterdayStr = yesterday.toISOString().split('T')[0];

        // Check if user voted today or yesterday to maintain streak
        if (daysArray[0] === todayStr || daysArray[0] === yesterdayStr) {
          currentStreak = 1;
          
          for (let i = 1; i < daysArray.length; i++) {
            const prevDate = new Date(daysArray[i - 1]);
            const currDate = new Date(daysArray[i]);
            const diffTime = prevDate.getTime() - currDate.getTime();
            const diffDays = Math.floor(diffTime / (1000 * 60 * 60 * 24));
            
            if (diffDays === 1) {
              currentStreak++;
              tempStreak++;
            } else {
              break;
            }
          }
        }

        // Calculate longest streak
        tempStreak = 1;
        for (let i = 1; i < daysArray.length; i++) {
          const prevDate = new Date(daysArray[i - 1]);
          const currDate = new Date(daysArray[i]);
          const diffTime = prevDate.getTime() - currDate.getTime();
          const diffDays = Math.floor(diffTime / (1000 * 60 * 60 * 24));
          
          if (diffDays === 1) {
            tempStreak++;
            longestStreak = Math.max(longestStreak, tempStreak);
          } else {
            tempStreak = 1;
          }
        }
        longestStreak = Math.max(longestStreak, currentStreak);

        const newStreakData = {
          currentStreak,
          longestStreak,
          lastVoteDate: daysArray[0],
        };
        
        setStreakData(newStreakData);
        await AsyncStorage.setItem(STREAK_KEY, JSON.stringify(newStreakData));
      }

      // Calculate vote statistics
      if (votes.length > 0) {
        let totalLikes = 0;
        let totalDislikes = 0;
        const categoryCount: Record<string, number> = {};
        const personVoteCount: Record<string, number> = {};

        votes.forEach((vote: any) => {
          // Count likes/dislikes
          if (vote.vote === 1) totalLikes++;
          else totalDislikes++;

          // Count by category
          const cat = vote.category || 'other';
          categoryCount[cat] = (categoryCount[cat] || 0) + 1;

          // Count by person
          personVoteCount[vote.personName] = (personVoteCount[vote.personName] || 0) + 1;
        });

        // Calculate category breakdown
        const categoriesBreakdown: CategoryStats[] = Object.entries(categoryCount)
          .map(([category, count]) => ({
            category,
            count,
            percentage: Math.round((count / votes.length) * 100),
          }))
          .sort((a, b) => b.count - a.count);

        // Find favorite category
        const favoriteCategory = categoriesBreakdown[0]?.category || '';

        // Find most voted person
        const mostVotedEntry = Object.entries(personVoteCount).sort((a, b) => b[1] - a[1])[0];
        const mostVotedPerson = mostVotedEntry
          ? { name: mostVotedEntry[0], count: mostVotedEntry[1] }
          : { name: '', count: 0 };

        setVoteStats({
          totalLikes,
          totalDislikes,
          categoriesBreakdown,
          favoriteCategory,
          mostVotedPerson,
        });
      }
    } catch (error) {
      console.error('Failed to load engagement data:', error);
    }
  }, []);

  useEffect(() => {
    loadEngagementData();
  }, [loadEngagementData]);

  return {
    badges,
    streakData,
    totalVotes,
    refreshEngagementData: loadEngagementData,
  };
}
